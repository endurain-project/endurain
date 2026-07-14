import { useRoute, useRouter } from 'vue-router'
import { getQueryString } from '@/composables/useRouteQuery'

export { getQueryString } from '@/composables/useRouteQuery'

/**
 * Custom URL schemes accepted as redirect targets — restricted to the app's
 * own native deep-link scheme. This is a deny-by-default allow-list: any scheme
 * not listed here is rejected, which blocks dangerous pseudo-schemes such as
 * `javascript:`, `data:`, and `vbscript:` that would otherwise execute when a
 * redirect value is assigned to `window.location.href`.
 */
const ALLOWED_CUSTOM_SCHEMES = ['endurain:'] as const

/**
 * Checks whether a redirect is an allowed native-app custom-scheme deep link
 * (e.g. `endurain://`).
 *
 * Only schemes in {@link ALLOWED_CUSTOM_SCHEMES} pass. `http(s)` URLs are
 * intentionally rejected here (they are treated as external redirects and
 * blocked), and script-bearing pseudo-schemes such as `javascript://...` are
 * rejected because they are not on the allow-list — preventing the open-redirect
 * check from being turned into a DOM-XSS vector.
 *
 * @param value - Redirect candidate.
 * @returns Whether the redirect is an allowed custom-scheme URL.
 */
export function isCustomSchemeRedirect(value: string): boolean {
  const scheme = /^([a-z][a-z0-9+.-]*:)\/\//i.exec(value)?.[1]?.toLowerCase()
  return scheme !== undefined && (ALLOWED_CUSTOM_SCHEMES as readonly string[]).includes(scheme)
}

/**
 * Resolves redirect query values while blocking external HTTP redirects, to
 * prevent open-redirect attacks. Only internal paths and custom-scheme deep
 * links are allowed; anything else falls back to the app root.
 *
 * @param value - Raw redirect query value.
 * @returns A safe internal path or custom-scheme URL, or `/` when unsafe.
 */
export function getSafeRedirect(value: unknown): string {
  const candidate = getQueryString(value)
  if (candidate.startsWith('/') && !candidate.startsWith('//') && !candidate.includes('://')) {
    return candidate
  }
  if (isCustomSchemeRedirect(candidate)) {
    return candidate
  }
  return '/'
}

/**
 * Redirect helpers bound to the active route/router. Centralises the
 * open-redirect protection used by every authentication entry point.
 *
 * @returns Safe redirect resolvers plus post-login navigation helpers.
 */
export function useSafeRedirect() {
  const route = useRoute()
  const router = useRouter()

  /**
   * Navigates to the post-login destination, honouring a safe `redirect`
   * query and supporting native-app custom schemes.
   */
  async function navigateAfterLogin(): Promise<void> {
    const redirect = getSafeRedirect(route.query.redirect)
    if (isCustomSchemeRedirect(redirect)) {
      window.location.href = redirect
      return
    }
    await router.replace(redirect)
  }

  /**
   * Returns a redirect value safe to forward to the backend SSO initiation
   * endpoint, or an empty string when the destination is the app root.
   *
   * @returns Internal path or custom-scheme URL, or an empty string.
   */
  function getSsoRedirect(): string {
    const redirect = getSafeRedirect(route.query.redirect)
    return redirect === '/' ? '' : redirect
  }

  return {
    getSafeRedirect,
    isCustomSchemeRedirect,
    getQueryString,
    navigateAfterLogin,
    getSsoRedirect,
  }
}
