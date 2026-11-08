import { useRoute, useRouter } from 'vue-router'

import type { IdentityProviderPublic } from '@/types'
import type { PublicServerSettings } from '@/features/config/types'

import { useAuthStore } from '@/features/auth/stores/auth'
import { generateCodeChallenge, generateCodeVerifier } from '@/features/auth/utils/pkce'
import { HttpError } from '@/services/http'
import { exchangeSessionForTokens, getIdentityProviderLoginUrl } from '@/services/identityProviders'
import { dropQueryParam } from '@/composables/useRouteQuery'
import { getQueryString, useSafeRedirect } from '@/composables/useSafeRedirect'
import { useTelemetry } from '@/composables/useTelemetry'

const PKCE_KEY = 'pkce_verifier'
const PKCE_VERIFIER_TTL_MS = 10 * 60 * 1000
const MFA_REQUIRED_PROBLEM = 'urn:endurain:error:mfa-required'

interface StoredPkceVerifier {
  verifier: string
  createdAt: number
}

/** Result of starting an SSO login. */
export type SsoStartResult = { status: 'redirecting' } | { status: 'error' }

/** Result of processing an SSO callback. */
export type SsoCallbackResult =
  | { status: 'none' }
  | { status: 'completed' }
  | { status: 'mfa-required' }
  | { status: 'error'; messageKey: string }

/** An SSO session whose exchange waits for the account's MFA code. */
interface PendingSsoMfa {
  sessionId: string
  verifier: string
}

/**
 * Reads the stored PKCE verifier and removes it when expired or malformed.
 *
 * @returns Stored verifier, or `null` when unavailable.
 */
function readStoredPkceVerifier(): StoredPkceVerifier | null {
  try {
    const raw = sessionStorage.getItem(PKCE_KEY)
    if (!raw) {
      return null
    }

    const parsed = JSON.parse(raw) as Partial<StoredPkceVerifier>
    if (
      typeof parsed.verifier !== 'string' ||
      parsed.verifier.length === 0 ||
      typeof parsed.createdAt !== 'number' ||
      Date.now() - parsed.createdAt > PKCE_VERIFIER_TTL_MS
    ) {
      sessionStorage.removeItem(PKCE_KEY)
      return null
    }

    return { verifier: parsed.verifier, createdAt: parsed.createdAt }
  } catch {
    sessionStorage.removeItem(PKCE_KEY)
    return null
  }
}

/**
 * Stores a verifier with a short TTL so abandoned redirects cannot linger for
 * the lifetime of the browser tab. A later start replaces an earlier one, so the
 * callback always uses the verifier of the latest sign-in.
 *
 * @param verifier - PKCE verifier to store.
 */
function storePkceVerifier(verifier: string): void {
  sessionStorage.setItem(
    PKCE_KEY,
    JSON.stringify({ verifier, createdAt: Date.now() } satisfies StoredPkceVerifier),
  )
}

/**
 * Encapsulates the SSO/PKCE login flow: initiating provider logins, handling
 * the backend callback, and the single-provider auto-redirect. Extracted from
 * the login view so the security-sensitive PKCE handling is reusable and
 * independently testable.
 *
 * @returns Actions to start SSO, process callbacks, and auto-redirect.
 */
export function useSsoLogin() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()
  const { getSafeRedirect, getSsoRedirect, isCustomSchemeRedirect, navigateAfterLogin } =
    useSafeRedirect()
  let pendingMfa: PendingSsoMfa | null = null

  /**
   * Exchanges an SSO session for web tokens and signs the user in.
   *
   * @param pending - The session to exchange, with its stored PKCE verifier.
   * @param mfaCode - MFA code, when the account has MFA enabled.
   * @throws {HttpError} When the exchange is refused.
   */
  async function exchangeAndSignIn(pending: PendingSsoMfa, mfaCode?: string): Promise<void> {
    const tokenData = mfaCode
      ? await exchangeSessionForTokens(pending.sessionId, pending.verifier, mfaCode)
      : await exchangeSessionForTokens(pending.sessionId, pending.verifier)
    sessionStorage.removeItem(PKCE_KEY)

    await auth.completeTokenLogin(tokenData)
    useTelemetry().trackEvent('login_succeeded', { method: 'sso' })
    await navigateAfterLogin()
  }

  /**
   * Starts an SSO login using the backend PKCE endpoints. On success the
   * browser navigates away to the identity provider.
   *
   * @param slug - Provider slug.
   * @returns Whether the redirect started or failed to initiate.
   */
  async function startSsoLogin(slug: string): Promise<SsoStartResult> {
    try {
      const verifier = generateCodeVerifier()
      const challenge = await generateCodeChallenge(verifier)
      storePkceVerifier(verifier)

      const params = new URLSearchParams({
        code_challenge: challenge,
        code_challenge_method: 'S256',
      })
      const redirect = getSsoRedirect()
      if (redirect) {
        params.set('redirect', redirect)
      }

      window.location.assign(getIdentityProviderLoginUrl(slug, params))
      return { status: 'redirecting' }
    } catch {
      return { status: 'error' }
    }
  }

  /**
   * Completes an SSO callback when the backend redirected back with a session
   * ID, exchanging it (plus the stored PKCE verifier) for web tokens.
   *
   * @returns Whether a callback was handled, completed, or failed.
   */
  async function processSsoCallback(): Promise<SsoCallbackResult> {
    if (route.query.sso !== 'success' || !route.query.session_id) {
      return { status: 'none' }
    }

    try {
      const sessionId = getQueryString(route.query.session_id)
      if (!sessionId) {
        throw new Error('Invalid session ID')
      }
      // The session id is single-use and already held here, so it does not stay in the history.
      dropQueryParam(route, router, 'session_id')

      // The flag comes from the URL, so it alone grants nothing: only the app's own
      // deep-link scheme may be navigated to with the session ID. Anything else
      // takes the normal token exchange below, which needs the stored PKCE verifier.
      const redirect = getSafeRedirect(route.query.redirect)
      if (route.query.external_redirect === 'true' && isCustomSchemeRedirect(redirect)) {
        const target = new URL(redirect)
        target.searchParams.set('session_id', sessionId)
        window.location.href = target.href
        // Custom schemes don't actually navigate the tab away, so this document
        // stays loaded. When the browser already has its own authenticated
        // session, fall back to the dashboard instead of leaving a stale login
        // form behind in case the OS handoff to the app doesn't happen (app not
        // installed, prompt dismissed, desktop testing, etc.).
        if (auth.isAuthenticated) {
          await router.replace({ name: 'home' })
        }
        return { status: 'completed' }
      }

      const stored = readStoredPkceVerifier()
      if (!stored) {
        throw new Error('Missing PKCE verifier')
      }

      const pending = { sessionId, verifier: stored.verifier }
      try {
        await exchangeAndSignIn(pending)
      } catch (error) {
        // The session stays usable, so the user can still finish with a code.
        if (error instanceof HttpError && error.type === MFA_REQUIRED_PROBLEM) {
          pendingMfa = pending
          return { status: 'mfa-required' }
        }
        throw error
      }
      return { status: 'completed' }
    } catch {
      return { status: 'error', messageKey: 'login.ssoTokenExchangeFailed' }
    }
  }

  /**
   * Finishes an SSO login that is waiting for the account's MFA code.
   *
   * @param mfaCode - TOTP or backup code.
   * @throws {HttpError} When the code is refused or the account is locked out.
   */
  async function completeSsoMfa(mfaCode: string): Promise<void> {
    if (!pendingMfa) {
      throw new Error('No SSO login is waiting for an MFA code')
    }
    await exchangeAndSignIn(pendingMfa, mfaCode)
    pendingMfa = null
  }

  /**
   * Redirects to the sole SSO provider when the server is configured for a
   * single-provider, SSO-only login and no callback is in progress.
   *
   * @param settings - Public server settings.
   * @param providers - Enabled SSO providers.
   * @param forceLocalLogin - Whether the user opted into local login.
   */
  function maybeAutoRedirect(
    settings: PublicServerSettings,
    providers: IdentityProviderPublic[],
    forceLocalLogin: boolean,
  ): void {
    const onlyProvider = providers[0]
    if (
      settings.sso_enabled &&
      settings.sso_auto_redirect &&
      !settings.local_login_enabled &&
      onlyProvider &&
      !forceLocalLogin &&
      route.query.sso !== 'success' &&
      !route.query.error
    ) {
      void startSsoLogin(onlyProvider.slug)
    }
  }

  return { startSsoLogin, processSsoCallback, completeSsoMfa, maybeAutoRedirect }
}
