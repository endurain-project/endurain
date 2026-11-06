import { ref } from 'vue'
import { defineStore } from 'pinia'

import type { AuthTokenResponse } from '@/types'
import type { LoginResponse, User } from '@/features/auth/types'

import { useTelemetry } from '@/composables/useTelemetry'
import { useRealtime } from '@/composables/useRealtime'
import { getLocaleForBackendLanguage, loadLocaleMessages, setI18nLocale } from '@/i18n'
import { clearUserScopedStorage } from '@/lib/storage'
import { queryClient } from '@/plugins/vueQuery'
import { clearAuthTokens, setAuthTokens } from '@/services/authTokens'
import { HttpError } from '@/services/http'
import { queryKeys } from '@/services/queryKeys'
import { fetchCurrentUser } from '@/features/auth/services/profile'
import {
  changePasswordAtLogin,
  loginWithPassword,
  logoutSession,
  refreshSession,
  verifyMfaLogin,
} from '@/features/auth/services/session'

export interface AuthCompletedResult {
  status: 'authenticated'
  user: User
}

export interface MfaRequiredResult {
  status: 'mfa-required'
  /** Names this login; the MFA step must send it back. */
  challenge: string
}

export interface PasswordChangeRequiredResult {
  status: 'password-change-required'
  /** Names this login; the password-change step must send it back. */
  challenge: string
}

/** The server asked for a step this client does not know, so the sign-in cannot continue. */
export interface UnsupportedStepResult {
  status: 'unsupported-step'
}

export type LoginResult =
  AuthCompletedResult | MfaRequiredResult | PasswordChangeRequiredResult | UnsupportedStepResult

type LoginMethod = 'password' | 'mfa' | 'password_change'

/**
 * Checks whether an auth error is an expected, non-reportable outcome (an
 * unauthenticated or absent session) rather than a real fault worth capturing.
 *
 * @param error - The caught error.
 * @returns Whether the error is an expected 401/404 auth response.
 */
function isExpectedAuthError(error: unknown): boolean {
  return error instanceof HttpError && [401, 404].includes(error.status)
}

let restorePromise: Promise<void> | null = null

/**
 * Applies the authenticated user's preferred backend language when v2 supports it.
 *
 * @param nextUser - Hydrated authenticated user.
 */
async function applyPreferredLocale(nextUser: User): Promise<void> {
  const locale = getLocaleForBackendLanguage(nextUser.preferredLanguage)
  if (!locale) {
    return
  }
  await loadLocaleMessages(locale)
  setI18nLocale(locale)
}

/**
 * Authentication *session authority* for the app shell. The store owns only
 * client-side session state (`isAuthenticated`, `sessionId`, `isReady`) plus
 * the credential lifecycle (login, refresh, logout). The authenticated user's
 * profile is **server state**: it is seeded into the TanStack Query cache here
 * and read everywhere through {@link useCurrentUser}, so Pinia is never a
 * server cache and there is a single source of truth for the user.
 */
export const useAuthStore = defineStore('auth', () => {
  const sessionId = ref<string | null>(null)
  const isReady = ref(false)
  const isAuthenticated = ref(false)

  /**
   * Completes a token response by storing tokens and hydrating the profile.
   * The resolved profile is written to the Query cache (the canonical read
   * path) rather than held on the store.
   *
   * @param response - Token response from login, MFA, or refresh.
   * @returns Authenticated result containing the current user.
   */
  async function completeTokenLogin(response: AuthTokenResponse): Promise<AuthCompletedResult> {
    setAuthTokens(response.access_token, response.csrf_token)
    sessionId.value = response.session_id
    let nextUser: User
    try {
      nextUser = await fetchCurrentUser()
    } catch (error) {
      // The tokens are valid but the profile fetch failed. Never leave tokens
      // in memory with no resolved user — reset to a clean logged-out state so
      // the UI doesn't get stuck half-authenticated.
      clearLocalSession()
      throw error
    }
    // Seed the Query cache so useCurrentUser() resolves without a redundant
    // fetch; the store stays out of the server-state business beyond this.
    queryClient.setQueryData(queryKeys.currentUser(), nextUser)
    isAuthenticated.value = true
    await applyPreferredLocale(nextUser)
    isReady.value = true
    // Open the realtime channel now that a session is established.
    useRealtime().connect()
    return { status: 'authenticated', user: nextUser }
  }

  /**
   * Continues a sign-in from the answer of the server, by its `next_step`. An
   * unknown step (a newer server) ends the attempt without touching the
   * session, so a later step can be added without breaking this client.
   *
   * @param response - Answer of the login, MFA or password-change request.
   * @param method - The step that produced the answer, for telemetry.
   * @returns Authenticated result, or the next step to show.
   */
  async function continueLogin(response: LoginResponse, method: LoginMethod): Promise<LoginResult> {
    switch (response.next_step) {
      case 'mfa':
        return { status: 'mfa-required', challenge: response.mfa_challenge }
      case 'password_change':
        return {
          status: 'password-change-required',
          challenge: response.password_change_challenge,
        }
      case 'tokens': {
        // The web client sends `X-Client-Type: web`, so the tokens carry a CSRF token.
        if (!('csrf_token' in response)) {
          return { status: 'unsupported-step' }
        }
        const result = await completeTokenLogin(response)
        useTelemetry().trackEvent('login_succeeded', { method })
        return result
      }
      default:
        return { status: 'unsupported-step' }
    }
  }

  /**
   * Authenticates with username/password.
   *
   * @param username - Username supplied by the user.
   * @param password - Password supplied by the user.
   * @returns Login result, including the MFA or password-change step when one is needed.
   * @throws {HttpError} When credentials are invalid or auth is unavailable.
   */
  async function login(username: string, password: string): Promise<LoginResult> {
    return continueLogin(await loginWithPassword(username, password), 'password')
  }

  /**
   * Completes a pending MFA login.
   *
   * @param challenge - The challenge the password step returned.
   * @param mfaCode - TOTP or backup code.
   * @returns Authenticated result, or the password-change step when the account needs one.
   * @throws {HttpError} When the MFA code or the challenge is invalid or expired.
   */
  async function verifyMfa(challenge: string, mfaCode: string): Promise<LoginResult> {
    return continueLogin(
      await verifyMfaLogin({ mfa_challenge: challenge, mfa_code: mfaCode }),
      'mfa',
    )
  }

  /**
   * Chooses the new password an administrator-set password requires and completes the sign-in.
   *
   * @param challenge - The challenge the earlier step returned.
   * @param password - The new password.
   * @returns Authenticated result.
   * @throws {HttpError} 401 when the challenge is unknown or expired; 422 when the password is refused.
   */
  async function changePassword(challenge: string, password: string): Promise<LoginResult> {
    return continueLogin(
      await changePasswordAtLogin({ password_change_challenge: challenge, password }),
      'password_change',
    )
  }

  /**
   * Restores a session after page reload using the HTTP-only refresh cookie.
   */
  async function restoreSession(): Promise<void> {
    if (isReady.value) {
      return
    }

    restorePromise ??= refreshSession()
      .then(async (response) => {
        await completeTokenLogin(response)
      })
      .catch((error: unknown) => {
        clearLocalSession()
        if (!isExpectedAuthError(error)) {
          useTelemetry().captureError(error, { scope: 'restoreSession' })
        }
      })
      .finally(() => {
        isReady.value = true
        restorePromise = null
      })

    await restorePromise
  }

  /**
   * Clears local auth state without contacting the backend. Clearing the Query
   * cache also drops the cached user profile, keeping a single source of truth.
   */
  function clearLocalSession(): void {
    isAuthenticated.value = false
    sessionId.value = null
    clearAuthTokens()
    clearUserScopedStorage()
    useRealtime().disconnect()
    queryClient.clear()
  }

  /**
   * Handles a terminal session expiry signalled by the HTTP layer (a
   * mid-session token refresh that failed). Clears local auth state and
   * reports whether a user had been authenticated, so the caller can decide
   * whether to redirect to the login screen.
   *
   * @returns Whether a user session was active when it expired.
   */
  function handleSessionExpired(): boolean {
    const wasAuthenticated = isAuthenticated.value
    clearLocalSession()
    isReady.value = true
    return wasAuthenticated
  }

  /**
   * Logs out from the backend and always clears local auth state.
   */
  async function logout(): Promise<void> {
    try {
      await logoutSession()
    } catch (error) {
      if (!isExpectedAuthError(error)) {
        useTelemetry().captureError(error, { scope: 'logout' })
      }
    } finally {
      clearLocalSession()
      isReady.value = true
      useTelemetry().trackEvent('logout')
    }
  }

  return {
    sessionId,
    isReady,
    isAuthenticated,
    completeTokenLogin,
    login,
    verifyMfa,
    changePassword,
    restoreSession,
    handleSessionExpired,
    clearLocalSession,
    logout,
  }
})
