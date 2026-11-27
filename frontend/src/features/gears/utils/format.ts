import type { Schemas } from '@/types'

import { kmToMiles } from '@/utils/units'

/** Currency symbols keyed by the backend currency code. */
const CURRENCY_SYMBOLS: Record<Schemas['Currency'], string> = {
  euro: '€',
  dollar: '$',
  pound: '£',
}

/**
 * Returns the display symbol for a currency code.
 *
 * @param currency - The backend currency code.
 * @returns The matching currency symbol.
 */
export function currencySymbol(currency: Schemas['Currency']): string {
  return CURRENCY_SYMBOLS[currency] ?? CURRENCY_SYMBOLS.euro
}

/**
 * Converts a distance in kilometres to the user's unit, rounded to one decimal.
 *
 * @param km - Distance in kilometres.
 * @param units - The user's measurement system.
 * @returns The distance in km (metric) or miles (imperial), to one decimal.
 */
export function kmToDisplayDistance(km: number, units: Schemas['Units']): number {
  const value = units === 'imperial' ? kmToMiles(km) : km
  return Math.round(value * 10) / 10
}

/**
 * Converts a distance in metres to the user's unit, rounded to one decimal.
 *
 * @param meters - Distance in metres.
 * @param units - The user's measurement system.
 * @returns The distance in km (metric) or miles (imperial), to one decimal.
 */
export function metersToDisplayDistance(meters: number, units: Schemas['Units']): number {
  return kmToDisplayDistance(meters / 1000, units)
}

/**
 * Splits a duration in seconds into whole hours and minutes (both floored), the
 * parts gear totals are summarized with.
 *
 * @param totalSeconds - Duration in seconds.
 * @returns The whole hours and the remaining whole minutes.
 */
export function splitDuration(totalSeconds: number): { hours: number; minutes: number } {
  const safe = Math.max(0, Math.floor(totalSeconds))
  return { hours: Math.floor(safe / 3600), minutes: Math.floor((safe % 3600) / 60) }
}
