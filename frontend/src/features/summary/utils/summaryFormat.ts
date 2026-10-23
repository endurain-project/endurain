/**
 * Formatters for aggregate summary metrics. Unlike the activities formatters
 * (which are pace/sport-aware), summary totals are plain rollups, so distance is
 * always shown in km/mi and duration as a compact `Hh Mm` clock. Each returns a
 * `{ value, unit }` split so callers can render the unit in a muted style.
 */

import type { Translate, Units } from '@/features/activities/utils/format'

import { kmToMiles } from '@/utils/units'

/** A formatted summary metric split into its value and unit. */
export interface SummaryMetric {
  /** The formatted numeric value (no unit). */
  value: string
  /** i18n key of the unit suffix (empty when unitless, e.g. for the activity count). */
  unit: string
}

/** Metres in one kilometre. */
const METERS_PER_KM = 1000
/** Metres to feet, for imperial elevation. */
const METERS_TO_FEET = 3.28084

/**
 * Combines a {@link SummaryMetric} into a single `value unit` string for dense
 * contexts such as breakdown table cells.
 *
 * @param metric - The split metric.
 * @param t - Translates the unit key.
 * @returns The combined string (just the value when there is no unit).
 */
export function combineSummaryMetric(metric: SummaryMetric, t: Translate): string {
  return metric.unit ? `${metric.value} ${t(metric.unit)}` : metric.value
}

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
  return {
    value: value.toFixed(2),
    unit: units === 'imperial' ? 'app.units.mi' : 'app.units.km',
  }
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
  return {
    value: Math.round(value).toString(),
    unit: units === 'imperial' ? 'app.units.ft' : 'app.units.m',
  }
}

/**
 * Formats an aggregate duration as a compact `Hh Mm` clock (`Mm` under an hour),
 * suited to large rollups that can span hundreds of hours.
 *
 * @param seconds - Total duration in seconds.
 * @param t - Translates the duration pattern.
 * @returns The formatted duration (the unit is embedded in the value).
 */
export function formatSummaryDuration(seconds: number, t: Translate): SummaryMetric {
  const whole = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const value =
    hours > 0
      ? t('app.units.hoursMinutes', { hours, minutes })
      : t('app.units.minutes', { minutes })
  return { value, unit: '' }
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
  return { value: grouped, unit: 'app.units.kcal' }
}
