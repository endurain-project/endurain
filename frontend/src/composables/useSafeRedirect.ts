import { useRoute, useRouter } from 'vue-router'
import { getQueryString } from '@/composables/useRouteQuery'

export { getQueryString } from '@/composables/useRouteQuery'

/**
 * Exact redirect addresses, from the server's `ALLOWED_REDIRECT_URIS`: custom-scheme deep
 * links and claimed-https addresses (Android App Links, iOS Universal Links). This is a
 * deny-by-default allow-list: only these addresses are accepted, which blocks dangerous
 * pseudo-schemes such as `javascript:`, `data:`, and `vbscript:` that would otherwise
 * execute when a redirect value is assigned to `window.location.href`. It is empty until
 * the public server settings load.
 */
let allowedRedirectUris = new Set<string>()

/**
 * Schemes that never become redirect targets, whatever the server configures:
 * `http` would be an unencrypted external redirect and the rest execute or embed content
 * when assigned to `window.location.href`. `https` is accepted only as a listed address
 * with a host (see {@link isHttpsAddressWithHost}).
 */
const UNSAFE_REDIRECT_SCHEMES = new Set(['http', 'javascript', 'data', 'vbscript', 'file', 'blob'])

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
 * Checks that an `https` address is `https://host...`: an authority with a host, no
 * user info, no whitespace or backslash, and a port the URL parser accepts. `new URL`
 * alone is not enough, as it reads `https:///x` as the host `x`.
 *
 * @param address - Address whose scheme is already lower case.
 * @returns Whether the address has a usable host.
 */
function isHttpsAddressWithHost(address: string): boolean {
  if (!address.startsWith('https://') || /[\s\\]/.test(address)) {
    return false
  }
  const authority = address.slice('https://'.length).split(/[/?#]/, 1)[0] ?? ''
  if (authority === '' || authority.includes('@')) {
    return false
  }
  try {
    return new URL(address).hostname !== ''
  } catch {
    return false
  }
}

/**
 * Replaces the allowed exact redirect addresses with the server's configured
 * list.
 *
 * Entries without a well-formed scheme or a target after it (`scheme:target`, the
 * `//` optional), whose scheme is in {@link UNSAFE_REDIRECT_SCHEMES}, or that are an
 * `https` address without a host, are ignored.
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
      if (scheme === 'https') {
        return isHttpsAddressWithHost(uri)
      }
      return uri.slice(scheme.length + 1).replace(/^\/\//, '') !== ''
    }),
  )
}

/**
 * Checks whether a redirect is an allowed native-app address: a custom-scheme deep link
 * (e.g. `app://callback` or `com.example.app:/callback`) or a claimed-https address
 * (e.g. `https://app.example.org/auth/sso/callback`).
 *
 * Only the addresses the server lists pass (scheme in any letter case, the rest exactly,
 * query and fragment included), so an unlisted `https` URL is an external redirect and
 * is rejected, as are script-bearing pseudo-schemes such as `javascript://...`, which
 * keeps the open-redirect check from becoming a DOM-XSS vector.
 *
 * @param value - Redirect candidate.
 * @returns Whether the redirect is an allowed native-app address.
 */
export function isNativeRedirect(value: string): boolean {
  return allowedRedirectUris.has(normaliseRedirectUri(value))
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
 * prevent open-redirect attacks. Only internal paths and listed native-app
 * addresses are allowed; anything else falls back to the app root.
 *
 * @param value - Raw redirect query value.
 * @returns A safe internal path or native-app address, or `/` when unsafe.
 */
export function getSafeRedirect(value: unknown): string {
  const candidate = getQueryString(value)
  if (hasUrlParserSensitiveChar(candidate)) {
    return '/'
  }
  if (isInternalPath(candidate) || isNativeRedirect(candidate)) {
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
   * query and supporting native-app addresses.
   */
  async function navigateAfterLogin(): Promise<void> {
    const redirect = getSafeRedirect(route.query.redirect)
    if (isNativeRedirect(redirect)) {
      window.location.href = redirect
      return
    }
    await router.replace(redirect)
  }

  /**
   * Returns a redirect value safe to forward to the backend SSO initiation
   * endpoint, or an empty string when the destination is the app root.
   *
   * @returns Internal path or native-app address, or an empty string.
   */
  function getSsoRedirect(): string {
    const redirect = getSafeRedirect(route.query.redirect)
    return redirect === '/' ? '' : redirect
  }

  return {
    getSafeRedirect,
    isNativeRedirect,
    getQueryString,
    navigateAfterLogin,
    getSsoRedirect,
  }
}
