import { useRoute, useRouter } from 'vue-router'

import type { IdentityProviderPublic } from '@/types'
import type { PublicServerSettings } from '@/features/config/types'

import {
  type AuthCompletedResult,
  type LoginResult,
  useAuthStore,
} from '@/features/auth/stores/auth'
import { generateCodeChallenge, generateCodeVerifier } from '@/features/auth/utils/pkce'
import { getIdentityProviderLoginUrl } from '@/services/identityProviders'
import { dropQueryParam } from '@/composables/useRouteQuery'
import { hasLoginStatusFlag } from '@/features/auth/composables/useLoginRouteMessages'
import { getQueryString, useSafeRedirect } from '@/composables/useSafeRedirect'

const PKCE_KEY = 'pkce_verifier'
const PKCE_VERIFIER_TTL_MS = 10 * 60 * 1000

interface StoredPkceVerifier {
  verifier: string
  createdAt: number
}

/** Result of starting an SSO login. */
export type SsoStartResult = { status: 'redirecting' } | { status: 'error' }

/**
 * Result of processing an SSO callback. `app-handoff` carries the custom-scheme address (with the
 * session ID) a native app gets only after the user confirms. `next-step` carries the step the login form shows next,
 * such as the MFA step of an account with MFA enabled.
 */
export type SsoCallbackResult =
  | { status: 'none' }
  | { status: 'completed' }
  | { status: 'app-handoff'; target: string }
  | { status: 'next-step'; result: Exclude<LoginResult, AuthCompletedResult> }
  | { status: 'error'; messageKey: string }

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
  const { getSafeRedirect, getSsoRedirect, isNativeRedirect, navigateAfterLogin } =
    useSafeRedirect()

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
   * Hands the session ID to the native app by navigating to its address.
   *
   * @param target - App address carrying the session ID.
   */
  async function continueAppHandoff(target: string): Promise<void> {
    window.location.href = target
    // A custom scheme doesn't navigate the tab away, so this document stays loaded;
    // a claimed https link may navigate away when the app isn't installed. When
    // the browser already has its own authenticated session, fall back to the
    // dashboard instead of leaving a stale login form behind in case the OS
    // handoff to the app doesn't happen (app not installed, prompt dismissed,
    // desktop testing, etc.).
    if (auth.isAuthenticated) {
      await router.replace({ name: 'home' })
    }
  }

  /**
   * Completes an SSO callback when the backend redirected back with a session
   * ID, exchanging it (plus the stored PKCE verifier) for web tokens. An account
   * with MFA enabled continues at the MFA step the password sign-in uses.
   *
   * @returns Whether a callback was handled, completed, needs another step, or failed.
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

      // The flag comes from the URL, so it alone grants nothing: only a native-app address
      // the server lists may be navigated to with the session ID. Anything else
      // takes the normal token exchange below, which needs the stored PKCE verifier.
      const redirect = getSafeRedirect(route.query.redirect)
      if (route.query.external_redirect === 'true' && isNativeRedirect(redirect)) {
        const target = new URL(redirect)
        target.searchParams.set('session_id', sessionId)
        // A custom scheme is not verified by the OS, so any app on the device may have registered it.
        // The user confirms before the session ID goes to it (RFC 8252 section 8.6). A claimed
        // https link is verified by the OS, so it is followed at once.
        if (target.protocol !== 'https:') {
          return { status: 'app-handoff', target: target.href }
        }
        await continueAppHandoff(target.href)
        return { status: 'completed' }
      }

      const stored = readStoredPkceVerifier()
      if (!stored) {
        throw new Error('Missing PKCE verifier')
      }

      const result = await auth.exchangeSsoSession(sessionId, stored.verifier)
      // The exchange has checked the verifier, so it is not needed again, not even by the MFA step.
      sessionStorage.removeItem(PKCE_KEY)
      if (result.status !== 'authenticated') {
        return { status: 'next-step', result }
      }
      await navigateAfterLogin()
      return { status: 'completed' }
    } catch {
      return { status: 'error', messageKey: 'login.ssoTokenExchangeFailed' }
    }
  }

  /**
   * Redirects to the sole SSO provider when the server is configured for a
   * single-provider, SSO-only login, no callback is in progress and the login
   * route carries no status message (such as signed out or session expired).
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
      !route.query.error &&
      !hasLoginStatusFlag(route.query)
    ) {
      void startSsoLogin(onlyProvider.slug)
    }
  }

  return { startSsoLogin, processSsoCallback, continueAppHandoff, maybeAutoRedirect }
}
