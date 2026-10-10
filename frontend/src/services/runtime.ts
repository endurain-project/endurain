import { API_PATH } from '@/constants/api'

/**
 * Removes a trailing slash from a URL-like value.
 *
 * @param value - URL-like string to normalize.
 * @returns The value without trailing slashes.
 */
function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

/**
 * Returns the runtime backend host configured by `/env.js`.
 *
 * @returns The configured backend host, or `null` when not set.
 */
export function getRuntimeBackendHost(): string | null {
  const host = window.env?.ENDURAIN_HOST?.trim()
  return host ? trimTrailingSlash(host) : null
}

/**
 * Resolves the API base URL using runtime config first, then build-time fallback.
 *
 * @returns API base URL without a trailing slash.
 */
export function getApiBaseUrl(): string {
  const runtimeHost = getRuntimeBackendHost()
  if (runtimeHost) {
    return `${runtimeHost}${API_PATH}`
  }

  const buildTimeUrl = import.meta.env.VITE_API_URL?.trim()
  return trimTrailingSlash(buildTimeUrl || API_PATH)
}

/**
 * Resolves a backend-served asset URL.
 *
 * Values that are already absolute (a presigned object-storage URL) are
 * returned untouched — prefixing them with the backend host would corrupt them.
 * Same-origin paths are resolved against the runtime host when one is set.
 *
 * @param path - Asset path relative to the backend host, or an absolute URL.
 * @returns Absolute URL when runtime host exists, otherwise same-origin path.
 */
export function getBackendAssetUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path
  }
  const normalizedPath = path.replace(/^\/+/, '')
  const runtimeHost = getRuntimeBackendHost()
  return runtimeHost ? `${runtimeHost}/${normalizedPath}` : `/${normalizedPath}`
}

/**
 * Resolves the realtime WebSocket URL, deriving the `ws`/`wss` scheme from the
 * API base URL so the backend `/api/v1` prefix is always included.
 *
 * @param path - WebSocket path appended to the API base (defaults to `/ws`).
 * @returns Absolute `ws(s)` URL without query parameters.
 */
export function getWebSocketUrl(path = '/ws'): string {
  const normalizedPath = `/${path.replace(/^\/+/, '')}`
  const apiBase = getApiBaseUrl()
  // getApiBaseUrl() may be absolute (runtime host / VITE_API_URL) or a relative
  // same-origin path (e.g. "/api/v1"); normalize to an absolute origin+path.
  const absoluteBase = /^https?:\/\//i.test(apiBase)
    ? apiBase
    : `${trimTrailingSlash(window.location.origin)}${apiBase}`
  // http -> ws, https -> wss.
  const wsBase = absoluteBase.replace(/^http/i, 'ws')
  return `${wsBase}${normalizedPath}`
}
