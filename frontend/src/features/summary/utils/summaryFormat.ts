/**
 * Formatters for aggregate summary metrics. Unlike the activities formatters
 * (which are pace/sport-aware), summary totals are plain rollups, so distance is
 * always shown in km/mi and duration as a compact `Hh Mm` clock. Each returns a
 * `{ value, unit }` split so callers can render the unit in a muted style.
 */

import type { Units } from '@/features/activities/utils/format'
import type { UnitKey } from '@/i18n'

import { kmToMiles } from '@/utils/units'

/** A formatted summary metric split into its value and unit. */
export interface SummaryMetric {
  /** The formatted numeric value (no unit). */
  value: string
  /** The unit key, or `null` for a unitless value. */
  unit: UnitKey | null
}

/** Metres in one kilometre. */
const METERS_PER_KM = 1000
/** Metres to feet, for imperial elevation. */
const METERS_TO_FEET = 3.28084

/**
 * Formats an aggregate distance in kilometres (metric) or miles (imperial),
 * with two decimal places.
 *
 * @param meters - Total distance in metres.
 * @param units - The user's unit system.
 * @returns The formatted distance and its unit.
 */
export function formatSummaryDistance(meters: number, units: Units): SummaryMetric {
  const km = meters / METERS_PER_KM
  const value = units === 'imperial' ? kmToMiles(km) : km
  return { value: value.toFixed(2), unit: units === 'imperial' ? 'mi' : 'km' }
}

/**
 * Formats an aggregate elevation gain in metres (metric) or feet (imperial),
 * rounded to a whole number.
 *
 * @param meters - Total elevation gain in metres.
 * @param units - The user's unit system.
 * @returns The formatted elevation and its unit.
 */
export function formatSummaryElevation(meters: number, units: Units): SummaryMetric {
  const value = units === 'imperial' ? meters * METERS_TO_FEET : meters
  return { value: Math.round(value).toString(), unit: units === 'imperial' ? 'ft' : 'm' }
}

/**
 * Formats an aggregate duration as a compact `Hh Mm` clock (`Mm` under an hour),
 * suited to large rollups that can span hundreds of hours. Returns the parts so the
 * view can render them with the localized duration format.
 *
 * @param seconds - Total duration in seconds.
 * @returns The whole hours and the remaining whole minutes.
 */
export function formatSummaryDuration(seconds: number): { hours: number; minutes: number } {
  const whole = Math.max(0, Math.floor(seconds))
  return { hours: Math.floor(whole / 3600), minutes: Math.floor((whole % 3600) / 60) }
}

/**
 * Formats an aggregate calorie total, rounded and grouped into thousands with a
 * comma (deterministic, locale-independent).
 *
 * @param calories - Total calories.
 * @returns The formatted calorie total and its unit.
 */
export function formatSummaryCalories(calories: number): SummaryMetric {
  const grouped = Math.round(calories)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return { value: grouped, unit: 'kcal' }
}
