/**
 * Health display formatters — pure functions that turn raw metric values into
 * the strings shown on the dashboard cards. Unit-system-aware values (weight,
 * water) convert via the shared `@/utils/units` helpers; threshold logic (BMI
 * category, HRV status) returns i18n key suffixes the view resolves to labels,
 * keeping the cutoffs unit-testable and out of the template.
 */

import type { Schemas } from '@/types'
import type { FastingSnapshot } from '@/features/health/types'

import { kgToLbs, mlToFlOz } from '@/utils/units'

type Units = Schemas['Units']

/**
 * Formats a duration in seconds as a compact `Hh Mm` string (e.g. `8h 5m`).
 *
 * @param seconds - Duration in seconds (clamped to zero if negative).
 * @returns The `Hh Mm` representation.
 */
export function formatHoursMinutes(seconds: number): string {
  const totalMinutes = Math.max(0, Math.round(seconds / 60))
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours}h ${minutes}m`
}

/**
 * Formats a duration in seconds as a zero-padded `HH:MM:SS` clock, used by the
 * live fasting timer where the seconds tick is meaningful.
 *
 * @param seconds - Elapsed duration in seconds (clamped to zero if negative).
 * @returns The `HH:MM:SS` representation.
 */
export function formatElapsedClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  const pad = (value: number): string => String(value).padStart(2, '0')
  return `${pad(hours)}:${pad(minutes)}:${pad(secs)}`
}

/**
 * Formats a resting heart rate as `52 bpm`.
 *
 * @param bpm - Resting heart rate in beats per minute.
 * @returns The formatted heart rate.
 */
export function formatRestingHeartRate(bpm: number): string {
  return `${Math.round(bpm)} bpm`
}

/**
 * Formats a skin-temperature deviation to one decimal place in °C.
 *
 * @param celsius - Deviation in degrees Celsius (may be negative).
 * @returns The formatted deviation.
 */
export function formatSkinTempDeviation(celsius: number): string {
  return `${celsius.toFixed(1)} °C`
}

/**
 * Formats a weight, converting to pounds for imperial users.
 *
 * @param weightKg - Weight in kilograms.
 * @param units - The user's unit system.
 * @returns The formatted weight (`72.0 kg` or `158.7 lb`).
 */
export function formatWeight(weightKg: number, units: Units): string {
  if (units === 'imperial') {
    return `${kgToLbs(weightKg).toFixed(1)} lb`
  }
  return `${weightKg.toFixed(1)} kg`
}

/**
 * Formats a mass (bone/muscle), converting to pounds for imperial users, to two
 * decimal places.
 *
 * @param massKg - Mass in kilograms.
 * @param units - The user's unit system.
 * @returns The formatted mass (`5.20 kg` or `11.46 lb`).
 */
export function formatBodyMass(massKg: number, units: Units): string {
  if (units === 'imperial') {
    return `${kgToLbs(massKg).toFixed(2)} lb`
  }
  return `${massKg.toFixed(2)} kg`
}

/**
 * Formats a `yyyy-mm-dd` health-entry date as a localized medium-style date
 * (e.g. `Jun 25, 2026`). The date is parsed from its parts as a *local* date so
 * the displayed day never drifts by a timezone offset (which a bare
 * `new Date('2026-06-25')` UTC parse would cause west of GMT).
 *
 * @param date - The measurement date as `yyyy-mm-dd`, or `null`.
 * @param locale - BCP-47 locale tag controlling the output language.
 * @returns The localized date, or an empty string when `date` is missing or unparseable.
 */
export function formatHealthEntryDate(date: string | null, locale = 'en'): string {
  if (!date) return ''
  const [year, month, day] = date.split('-').map(Number)
  if (!year || !month || !day) return ''
  const parsed = new Date(year, month - 1, day)
  return Number.isNaN(parsed.getTime())
    ? ''
    : new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(parsed)
}

/**
 * Formats a Body Mass Index to one decimal place.
 *
 * @param bmi - The BMI value.
 * @returns The formatted BMI.
 */
export function formatBmi(bmi: number): string {
  return bmi.toFixed(1)
}

/**
 * Formats a step count with locale-aware thousands separators.
 *
 * @param steps - The step count.
 * @returns The formatted step count.
 */
export function formatSteps(steps: number): string {
  return Math.round(steps).toLocaleString()
}

/**
 * Formats a water volume, converting to US fluid ounces for imperial users.
 *
 * @param amountMl - Volume in millilitres.
 * @param units - The user's unit system.
 * @returns The formatted volume (`1500 ml` or `50.7 fl oz`).
 */
export function formatWater(amountMl: number, units: Units): string {
  if (units === 'imperial') {
    return `${mlToFlOz(amountMl).toFixed(1)} fl oz`
  }
  return `${Math.round(amountMl)} ml`
}

/**
 * Resolves the i18n key suffix for a BMI category (WHO classification).
 *
 * @param bmi - The BMI value.
 * @returns The category key suffix (e.g. `bmiNormalWeight`).
 */
export function bmiCategoryKey(bmi: number): string {
  if (bmi < 18.5) return 'bmiUnderweight'
  if (bmi < 25) return 'bmiNormalWeight'
  if (bmi < 30) return 'bmiOverweight'
  if (bmi < 35) return 'bmiObesityClass1'
  if (bmi < 40) return 'bmiObesityClass2'
  return 'bmiObesityClass3'
}

/**
 * Maps an HRV status string to its i18n key suffix, or `null` when the status
 * is unrecognised.
 *
 * @param status - The backend HRV status (case-insensitive).
 * @returns The key suffix (e.g. `hrvBalanced`), or `null`.
 */
export function hrvStatusKey(status: string): string | null {
  switch (status.toUpperCase()) {
    case 'BALANCED':
      return 'hrvBalanced'
    case 'UNBALANCED':
      return 'hrvUnbalanced'
    case 'LOW':
      return 'hrvLow'
    case 'POOR':
      return 'hrvPoor'
    default:
      return null
  }
}

/**
 * Maps a sleep sub-score string to its i18n key suffix, or `null` when the
 * score is unrecognised. Shared by the overall score and every sub-score
 * (duration, quality, stage percentages, awake count).
 *
 * @param score - The backend sleep score (case-insensitive).
 * @returns The key suffix (e.g. `scoreExcellent`), or `null`.
 */
export function sleepScoreKey(score: string): string | null {
  switch (score.toUpperCase()) {
    case 'EXCELLENT':
      return 'scoreExcellent'
    case 'GOOD':
      return 'scoreGood'
    case 'FAIR':
      return 'scoreFair'
    case 'POOR':
      return 'scorePoor'
    default:
      return null
  }
}

/**
 * Seconds elapsed in a fasting session: computed live from the start time while
 * the fast is ongoing, otherwise the recorded duration.
 *
 * @param fasting - The fasting snapshot.
 * @param now - Current epoch milliseconds (injectable for testing).
 * @returns The elapsed seconds (never negative).
 */
export function fastingElapsedSeconds(fasting: FastingSnapshot, now: number = Date.now()): number {
  if (fasting.status === 'in_progress') {
    const start = new Date(fasting.startTime).getTime()
    return Math.max(0, Math.floor((now - start) / 1000))
  }
  return fasting.actualDurationSeconds ?? 0
}

/**
 * Current local time as a `yyyy-mm-ddTHH:mm` value for `<input type="datetime-local">`.
 *
 * The input element speaks local wall clock, so the UTC offset is subtracted
 * before slicing the ISO string.
 *
 * @returns The current local wall clock in `datetime-local` form.
 */
export function nowDateTimeLocalInput(): string {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

/**
 * Converts a stored UTC instant to the `datetime-local` value for the viewer.
 *
 * @param value - ISO 8601 instant from the API.
 * @returns The local wall clock in `datetime-local` form, or `''` when unparseable.
 */
export function toDateTimeLocalInput(value: string | null): string {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

/**
 * Converts a `datetime-local` value back to an unambiguous UTC ISO instant.
 *
 * `<input type="datetime-local">` yields an offset-less string; sending it as-is
 * makes the backend read the viewer's wall clock as if it were UTC, storing an
 * instant that is wrong by their offset. `new Date(local)` parses the
 * offset-less form as local time (per spec), which is exactly what is wanted.
 *
 * @param local - The `yyyy-mm-ddTHH:mm` input value.
 * @returns A UTC ISO string, or `null` when empty/unparseable.
 */
export function dateTimeLocalToIso(local: string): string | null {
  if (!local) {
    return null
  }
  const ms = new Date(local).getTime()
  return Number.isNaN(ms) ? null : new Date(ms).toISOString()
}

/**
 * The viewer's local calendar day (`yyyy-mm-dd`) for a stored UTC instant.
 *
 * Slicing the ISO string yields the **UTC** day, which puts a late-evening entry
 * in an eastern timezone on tomorrow and an early-morning one in a western
 * timezone on yesterday. Used for grouping entries into daily buckets.
 *
 * @param iso - ISO 8601 instant from the API.
 * @returns The local `yyyy-mm-dd`, or `null` when unparseable.
 */
export function localDayOf(iso: string | null): string | null {
  if (!iso) {
    return null
  }
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return null
  }
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
