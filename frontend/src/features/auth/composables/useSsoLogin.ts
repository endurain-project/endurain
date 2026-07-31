import { useRoute, useRouter } from 'vue-router'

import type { AuthTokenResponse, IdentityProviderPublic } from '@/types'
import type { PublicServerSettings } from '@/features/config/types'

import { useAuthStore } from '@/features/auth/stores/auth'
import { generateCodeChallenge, generateCodeVerifier } from '@/features/auth/utils/pkce'
import { exchangeSessionForTokens, getIdentityProviderLoginUrl } from '@/services/identityProviders'
import { getQueryString, useSafeRedirect } from '@/composables/useSafeRedirect'
import { useTelemetry } from '@/composables/useTelemetry'

const PKCE_PREFIX = 'pkce_verifier_'
const PKCE_VERIFIER_TTL_MS = 10 * 60 * 1000

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
  | { status: 'error'; messageKey: string }

/**
 * Finds the PKCE verifier stored before redirecting to the IdP.
 *
 * @returns Verifier plus storage key, or `null` when absent.
 */
function findStoredPkceVerifier(): { key: string; verifier: string } | null {
  const now = Date.now()
  for (let index = 0; index < sessionStorage.length; index += 1) {
    const key = sessionStorage.key(index)
    if (key?.startsWith(PKCE_PREFIX)) {
      const stored = readStoredPkceVerifier(key, now)
      if (stored) {
        return { key, verifier: stored.verifier }
      }
    }
  }
  return null
}

/**
 * Reads a stored PKCE verifier and removes it when expired or malformed.
 *
 * @param key - Storage key to read.
 * @param now - Current timestamp used for TTL validation.
 * @returns Stored verifier, or `null` when unavailable.
 */
function readStoredPkceVerifier(key: string, now = Date.now()): StoredPkceVerifier | null {
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) {
      return null
    }

    const parsed = JSON.parse(raw) as Partial<StoredPkceVerifier>
    if (
      typeof parsed.verifier !== 'string' ||
      parsed.verifier.length === 0 ||
      typeof parsed.createdAt !== 'number' ||
      now - parsed.createdAt > PKCE_VERIFIER_TTL_MS
    ) {
      sessionStorage.removeItem(key)
      return null
    }

    return { verifier: parsed.verifier, createdAt: parsed.createdAt }
  } catch {
    sessionStorage.removeItem(key)
    return null
  }
}

/**
 * Stores a verifier with a short TTL so abandoned redirects cannot linger for
 * the lifetime of the browser tab.
 *
 * @param slug - Provider slug.
 * @param verifier - PKCE verifier to store.
 */
function storePkceVerifier(slug: string, verifier: string): void {
  cleanupExpiredPkceVerifiers()
  sessionStorage.setItem(
    `${PKCE_PREFIX}${slug}`,
    JSON.stringify({ verifier, createdAt: Date.now() } satisfies StoredPkceVerifier),
  )
}

/**
 * Removes expired or malformed PKCE verifier records only.
 */
function cleanupExpiredPkceVerifiers(): void {
  const now = Date.now()
  for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = sessionStorage.key(index)
    if (key?.startsWith(PKCE_PREFIX)) {
      readStoredPkceVerifier(key, now)
    }
  }
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
  const { getSafeRedirect, getSsoRedirect, navigateAfterLogin } = useSafeRedirect()

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
      storePkceVerifier(slug, verifier)

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
      cleanupExpiredPkceVerifiers()
      const sessionId = getQueryString(route.query.session_id)
      if (!sessionId) {
        throw new Error('Invalid session ID')
      }

      if (route.query.external_redirect === 'true') {
        const redirect = getSafeRedirect(route.query.redirect)
        const separator = redirect.includes('?') ? '&' : '?'
        window.location.href = `${redirect}${separator}session_id=${encodeURIComponent(sessionId)}`
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

      const stored = findStoredPkceVerifier()
      if (!stored) {
        throw new Error('Missing PKCE verifier')
      }

      const tokenData = await exchangeSessionForTokens(sessionId, stored.verifier)
      sessionStorage.removeItem(stored.key)

      if (!tokenData.csrf_token) {
        throw new Error('Missing CSRF token')
      }

      await auth.completeTokenLogin({
        session_id: tokenData.session_id,
        access_token: tokenData.access_token,
        csrf_token: tokenData.csrf_token,
        token_type: 'bearer',
        expires_in: tokenData.expires_in,
        refresh_token_expires_in: tokenData.refresh_token_expires_in,
      } satisfies AuthTokenResponse)
      useTelemetry().trackEvent('login_succeeded', { method: 'sso' })
      await navigateAfterLogin()
      return { status: 'completed' }
    } catch {
      return { status: 'error', messageKey: 'login.ssoTokenExchangeFailed' }
    }
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

  return { startSsoLogin, processSsoCallback, maybeAutoRedirect }
}
