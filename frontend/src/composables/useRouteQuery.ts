import { watch, type ComputedRef } from 'vue'
import {
  useRoute,
  useRouter,
  type LocationQueryRaw,
  type RouteLocationNormalizedLoaded,
  type Router,
} from 'vue-router'

/**
 * Resolves a route query value to its first string value.
 *
 * @param value - Raw route query value.
 * @returns The first string value, or an empty string.
 */
export function getQueryString(value: unknown): string {
  const candidate = Array.isArray(value) ? value[0] : value
  return typeof candidate === 'string' ? candidate : ''
}

/**
 * Resolves a route query value only when it is a single string.
 *
 * @param value - Raw route query value.
 * @returns The string value, or an empty string for arrays and non-string values.
 */
export function getScalarQueryString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

/**
 * Removes one query parameter from the address bar and the history entry, keeping the others.
 *
 * @param route - The current route.
 * @param router - The router that replaces the entry.
 * @param key - The query parameter to remove.
 */
export function dropQueryParam(
  route: RouteLocationNormalizedLoaded,
  router: Router,
  key: string,
): void {
  const { [key]: _dropped, ...query } = route.query
  void router.replace({ query, hash: route.hash })
}

/** A one-time credential read from the URL, and a way to forget it. */
export interface QueryCredential {
  /** The credential, or an empty string when absent or malformed. */
  value: string
  /** Forgets the stored copy once the credential was used or refused for good. */
  clear: () => void
}

/**
 * Reads a one-time credential from the URL and removes it from the address bar, so it does not stay in
 * the history, a bookmark or a shared screenshot. The tab's session storage keeps a copy, so a reload
 * (which no longer has it in the URL) still finds it; it goes away with the tab or when cleared.
 *
 * @param key - The query parameter that carries the credential.
 * @returns The credential and a function that forgets it.
 */
export function useQueryCredential(key: string): QueryCredential {
  const route = useRoute()
  const router = useRouter()
  const storageKey = `endurain:credential:${route.path}:${key}`
  const fromUrl = getScalarQueryString(route.query[key])
  if (fromUrl) {
    dropQueryParam(route, router, key)
    writeSession(storageKey, fromUrl)
  }
  return {
    value: fromUrl || readSession(storageKey),
    clear: () => removeSession(storageKey),
  }
}

/**
 * Reads a session-storage value, treating blocked storage as empty.
 *
 * @param key - The storage key.
 * @returns The stored value, or an empty string.
 */
function readSession(key: string): string {
  try {
    return sessionStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

/**
 * Writes a session-storage value; best-effort when storage is blocked.
 *
 * @param key - The storage key.
 * @param value - The value to keep.
 */
function writeSession(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value)
  } catch {
    // Without storage the credential lives only for this page load.
  }
}

/**
 * Removes a session-storage value; best-effort when storage is blocked.
 *
 * @param key - The storage key.
 */
function removeSession(key: string): void {
  try {
    sessionStorage.removeItem(key)
  } catch {
    // Nothing to forget if storage is blocked.
  }
}

/**
 * Parses an activity type filter query param, where `0` represents all types.
 *
 * @param value - Raw route query value.
 * @returns A non-negative integer activity type code, or `0` when invalid.
 */
export function parseActivityTypeFilterQuery(value: unknown): number {
  const raw = getScalarQueryString(value)
  const parsed = raw ? Number(raw) : Number.NaN
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : 0
}

/**
 * Parses an ISO calendar-date query param.
 *
 * @param value - Raw route query value.
 * @param fallback - Value returned for absent or malformed dates.
 * @returns A `YYYY-MM-DD` value or the fallback.
 */
export function parseIsoDateQuery(value: unknown, fallback = ''): string {
  const raw = getScalarQueryString(value)
  return /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : fallback
}

/**
 * Replaces the current route query whenever the supplied state changes.
 *
 * @param queryState - Computed query values to persist in the active route.
 * @returns Nothing.
 */
export function useRouteQueryReplacement(queryState: ComputedRef<LocationQueryRaw>): void {
  const router = useRouter()

  watch(
    queryState,
    (query) => {
      void router.replace({ query }).catch(() => {})
    },
    { immediate: true },
  )
}
