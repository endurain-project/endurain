import { useRoute, useRouter } from 'vue-router'
import { getQueryString } from '@/composables/useRouteQuery'

export { getQueryString } from '@/composables/useRouteQuery'

/**
 * Custom URL schemes accepted as redirect targets. This is a deny-by-default
 * allow-list: any scheme not listed here is rejected, which blocks dangerous
 * pseudo-schemes such as `javascript:`, `data:`, and `vbscript:` that would
 * otherwise execute when a redirect value is assigned to `window.location.href`.
 * It starts with the app's own native deep-link scheme and is replaced by the
 * server's `ALLOWED_REDIRECT_SCHEMES` once the public server settings load.
 */
const DEFAULT_CUSTOM_SCHEMES = ['endurain']
let allowedCustomSchemes = new Set(DEFAULT_CUSTOM_SCHEMES)

/**
 * Schemes that never become redirect targets, whatever the server configures:
 * `http(s)` would be an external redirect and the rest execute or embed content
 * when assigned to `window.location.href`.
 */
const UNSAFE_REDIRECT_SCHEMES = new Set(['http', 'https', 'javascript', 'data', 'vbscript', 'file'])

/**
 * Replaces the allowed custom redirect schemes with the server's configured
 * list, so the frontend accepts exactly what the backend accepts.
 *
 * Entries that are not well-formed URI schemes, or that are in
 * {@link UNSAFE_REDIRECT_SCHEMES}, are ignored. An empty result leaves no custom
 * scheme allowed.
 *
 * @param schemes - Scheme names from the public server settings (without `:`).
 */
export function setAllowedRedirectSchemes(schemes: readonly string[]): void {
  allowedCustomSchemes = new Set(
    schemes
      .map((scheme) => scheme.toLowerCase())
      .filter(
        (scheme) => /^[a-z][a-z0-9+.-]*$/.test(scheme) && !UNSAFE_REDIRECT_SCHEMES.has(scheme),
      ),
  )
}

/**
 * Checks whether a redirect is an allowed native-app custom-scheme deep link
 * (e.g. `endurain://`).
 *
 * Only schemes configured on the server pass. `http(s)` URLs are intentionally
 * rejected here (they are treated as external redirects and blocked), and
 * script-bearing pseudo-schemes such as `javascript://...` are rejected because
 * they are not on the allow-list — preventing the open-redirect check from being
 * turned into a DOM-XSS vector.
 *
 * @param value - Redirect candidate.
 * @returns Whether the redirect is an allowed custom-scheme URL.
 */
export function isCustomSchemeRedirect(value: string): boolean {
  const scheme = /^([a-z][a-z0-9+.-]*):\/\//i.exec(value)?.[1]?.toLowerCase()
  return scheme !== undefined && allowedCustomSchemes.has(scheme)
}

/**
 * Origin used only to resolve a candidate path the way a browser would. It is never
 * navigated to; a path that resolves anywhere else escapes the application.
 */
const INTERNAL_ORIGIN = 'https://internal.invalid'

/**
 * Checks for characters a browser's URL parser treats specially inside a path:
 * ASCII control characters (tab, CR and LF are silently dropped, so `/<tab>/host`
 * becomes `//host`) and the backslash (read as `/`, so `/\host` becomes `//host`).
 * A string check on the raw value cannot see either, so they are rejected outright.
 *
 * @param value - Redirect candidate.
 * @returns Whether the value contains such a character.
 */
function hasUrlParserSensitiveChar(value: string): boolean {
  return Array.from(value).some((char) => {
    const code = char.codePointAt(0) ?? 0
    return code <= 0x1f || code === 0x7f || char === '\\'
  })
}

/**
 * Checks whether a candidate is a path that stays inside the application.
 *
 * @param candidate - Redirect candidate.
 * @returns Whether the browser would resolve it on the application's own origin.
 */
function isInternalPath(candidate: string): boolean {
  if (!candidate.startsWith('/') || candidate.includes('://')) {
    return false
  }
  try {
    return new URL(candidate, INTERNAL_ORIGIN).origin === INTERNAL_ORIGIN
  } catch {
    return false
  }
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
  if (hasUrlParserSensitiveChar(candidate)) {
    return '/'
  }
  if (isInternalPath(candidate) || isCustomSchemeRedirect(candidate)) {
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
