import { watch, type ComputedRef } from 'vue'
import {
  useRoute,
  useRouter,
  type LocationQueryRaw,
  type RouteLocationNormalizedLoaded,
  type Router,
} from 'vue-router'

import type { ActivityType } from '@/features/activities/types'
import { isActivityType } from '@/features/activities/utils/activityType'

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
 * Query parameters that carry a one-time or OAuth credential. They never travel in a login redirect: the
 * interrupted action restarts after sign-in instead of replaying a spent credential.
 */
export const ONE_TIME_CREDENTIAL_KEYS: ReadonlySet<string> = new Set([
  'code',
  'state',
  'iss',
  'error',
  'error_description',
  'session_state',
  'ticket',
  'token',
  'step_up_ticket',
  'step_up_error',
  'session_id',
  'sso',
  'idp_link',
])

/**
 * Builds the address a login redirect returns to: the path and the query without the one-time credentials,
 * and without the fragment (it can hold a credential and would reach the server through the SSO start).
 *
 * @param target - The route the visitor was blocked from.
 * @returns The path, followed by `?` and the remaining query when there is one.
 */
export function getLoginRedirect(
  target: Pick<RouteLocationNormalizedLoaded, 'path' | 'query'>,
): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(target.query)) {
    if (ONE_TIME_CREDENTIAL_KEYS.has(key)) {
      continue
    }
    for (const item of Array.isArray(value) ? value : [value]) {
      params.append(key, item ?? '')
    }
  }
  const query = params.toString()
  return query ? `${target.path}?${query}` : target.path
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

/**
 * Reads a one-time credential from the URL fragment, falling back to the query string for links sent before
 * the credential moved to the fragment, and removes it from the address bar so it does not stay in the
 * history, a bookmark or a shared screenshot. The fragment is never sent to a server or logged by a proxy.
 * The credential is not stored: after a reload the link is needed again.
 *
 * @param key - The fragment or query parameter that carries the credential.
 * @returns The credential, or an empty string when absent or malformed.
 */
export function useUrlCredential(key: string): string {
  const route = useRoute()
  const router = useRouter()
  const fragment = new URLSearchParams(route.hash.replace(/^#/, ''))
  const fromFragment = fragment.get(key) ?? ''
  const fromQuery = getScalarQueryString(route.query[key])
  if (fromFragment || key in route.query) {
    const { [key]: _dropped, ...query } = route.query
    fragment.delete(key)
    const rest = fragment.toString()
    void router.replace({ query, hash: rest ? `#${rest}` : '' })
  }
  return fromFragment || fromQuery
}

/**
 * Parses an activity type filter query param, where the empty string represents all types.
 *
 * @param value - Raw route query value.
 * @returns The activity type, or the empty string when absent or unknown.
 */
export function parseActivityTypeFilterQuery(value: unknown): ActivityType | '' {
  const raw = getScalarQueryString(value)
  return isActivityType(raw) ? raw : ''
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
