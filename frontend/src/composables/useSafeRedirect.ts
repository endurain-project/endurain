import { useRoute, useRouter } from 'vue-router'
import { getQueryString } from '@/composables/useRouteQuery'

export { getQueryString } from '@/composables/useRouteQuery'

/**
 * Custom URL schemes accepted as redirect targets. This is a deny-by-default
 * allow-list: any scheme not listed here is rejected, which blocks dangerous
 * pseudo-schemes such as `javascript:`, `data:`, and `vbscript:` that would
 * otherwise execute when a redirect value is assigned to `window.location.href`.
 * It starts with the app's own native deep-link scheme and is replaced by the
 * server's `ALLOWED_REDIRECT_SCHEMES` once the public server settings load, unless the
 * server lists exact addresses (`ALLOWED_REDIRECT_URIS`).
 */
const DEFAULT_CUSTOM_SCHEMES = ['endurain']
let allowedCustomSchemes = new Set(DEFAULT_CUSTOM_SCHEMES)

/**
 * Exact redirect addresses, from the server's `ALLOWED_REDIRECT_URIS`. While any is set,
 * only these are accepted and the schemes are ignored.
 */
let allowedRedirectUris = new Set<string>()

/**
 * Schemes that never become redirect targets, whatever the server configures:
 * `http(s)` would be an external redirect and the rest execute or embed content
 * when assigned to `window.location.href`.
 */
const UNSAFE_REDIRECT_SCHEMES = new Set([
  'http',
  'https',
  'javascript',
  'data',
  'vbscript',
  'file',
  'blob',
])

/** RFC 3986 3.1: `scheme = ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )`. */
const SCHEME_PATTERN = /^[a-z][a-z0-9+.-]*$/i

/**
 * Reads the scheme of an absolute URI. It runs up to the first `:` (RFC 3986 3.1),
 * so `app:/callback` and `app://callback` both have the scheme `app`; a value
 * starting with `/` never has one, because a scheme starts with a letter.
 *
 * @param uri - Value to read.
 * @returns The scheme in lower case, or `undefined` when the value has none.
 */
function uriScheme(uri: string): string | undefined {
  const index = uri.indexOf(':')
  const scheme = index < 0 ? '' : uri.slice(0, index)
  return SCHEME_PATTERN.test(scheme) ? scheme.toLowerCase() : undefined
}

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
      .filter((scheme) => SCHEME_PATTERN.test(scheme) && !UNSAFE_REDIRECT_SCHEMES.has(scheme)),
  )
}

/**
 * Lower-cases the scheme of an address and keeps the rest as written, the form in
 * which the server compares addresses.
 *
 * @param uri - Address to normalise.
 * @returns The address with its scheme in lower case, or unchanged when it has none.
 */
function normaliseRedirectUri(uri: string): string {
  const scheme = uriScheme(uri)
  return scheme === undefined ? uri : scheme + uri.slice(scheme.length)
}

/**
 * Replaces the allowed exact redirect addresses with the server's configured
 * list. While the list is not empty, only these addresses are accepted.
 *
 * Entries without a well-formed scheme or a target after it (`scheme:target`, the
 * `//` optional), or whose scheme is in {@link UNSAFE_REDIRECT_SCHEMES}, are ignored.
 *
 * @param uris - Addresses from the public server settings.
 */
export function setAllowedRedirectUris(uris: readonly string[]): void {
  allowedRedirectUris = new Set(
    uris.map(normaliseRedirectUri).filter((uri) => {
      const scheme = uriScheme(uri)
      if (scheme === undefined || UNSAFE_REDIRECT_SCHEMES.has(scheme)) {
        return false
      }
      return uri.slice(scheme.length + 1).replace(/^\/\//, '') !== ''
    }),
  )
}

/**
 * Checks whether a redirect is an allowed native-app custom-scheme deep link
 * (e.g. `endurain://callback` or `endurain:/callback`).
 *
 * When the server lists exact addresses, only those pass (scheme in any letter case,
 * the rest exactly, query and fragment included). Otherwise only schemes configured
 * on the server pass. `http(s)` URLs are intentionally
 * rejected here (they are treated as external redirects and blocked), and
 * script-bearing pseudo-schemes such as `javascript://...` are rejected because
 * they are not on the allow-list — preventing the open-redirect check from being
 * turned into a DOM-XSS vector.
 *
 * @param value - Redirect candidate.
 * @returns Whether the redirect is an allowed custom-scheme URL.
 */
export function isCustomSchemeRedirect(value: string): boolean {
  if (allowedRedirectUris.size > 0) {
    return allowedRedirectUris.has(normaliseRedirectUri(value))
  }
  const scheme = uriScheme(value)
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
