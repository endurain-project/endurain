import { watch, type ComputedRef } from 'vue'
import { useRouter, type LocationQueryRaw } from 'vue-router'

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
