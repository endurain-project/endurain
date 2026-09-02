/**
 * Date/time formatting helpers — the first of the v1 domain utilities to be
 * ported. Kept as pure functions (no Vue, no i18n instance) so they are trivial
 * to unit-test and can be reused by any view or composable. Locale-aware output
 * is delegated to the platform `Intl` APIs rather than a bundled date library.
 */

import type { Schemas } from '@/types'

const MS_PER_DAY = 86_400_000

const WEEKDAY_UTC_INDEX: Record<Schemas['WeekDay'], number> = {
  sunday: 0,
  monday: 1,
  tuesday: 2,
  wednesday: 3,
  thursday: 4,
  friday: 5,
  saturday: 6,
}

/** Parses a `YYYY-MM-DD` string into a UTC `Date` at midnight. */
function parseIsoDate(iso: string): Date {
  const parts = iso.split('-')
  const year = Number(parts[0])
  const month = Number(parts[1] ?? 1)
  const day = Number(parts[2] ?? 1)
  return new Date(Date.UTC(year, month - 1, day))
}

/** Formats a `Date` as a `YYYY-MM-DD` string using its UTC fields. */
function toIsoDate(date: Date): string {
  const year = date.getUTCFullYear()
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Largest magnitude (in the current unit) before rolling up to the next unit,
 * paired with the `Intl.RelativeTimeFormat` unit it represents. Ordered from
 * smallest to largest so the formatter can divide down the chain.
 */
const RELATIVE_TIME_DIVISIONS: ReadonlyArray<{
  amount: number
  unit: Intl.RelativeTimeFormatUnit
}> = [
  { amount: 60, unit: 'seconds' },
  { amount: 60, unit: 'minutes' },
  { amount: 24, unit: 'hours' },
  { amount: 7, unit: 'days' },
  { amount: 4.34524, unit: 'weeks' },
  { amount: 12, unit: 'months' },
  { amount: Number.POSITIVE_INFINITY, unit: 'years' },
]

/**
 * Formats a timestamp as a localized, human-friendly relative string such as
 * "3 minutes ago", "yesterday", or "in 2 days". Past timestamps yield negative
 * phrasing, future ones positive, using `Intl.RelativeTimeFormat` so the wording
 * follows the active locale's rules.
 *
 * @param value - The instant to describe, as an ISO string or `Date`.
 * @param now - The reference "now" to measure against; defaults to the current
 *   time. Injectable so tests are deterministic.
 * @param locale - BCP-47 locale tag controlling the output language.
 * @returns The localized relative-time phrase, or an empty string when `value`
 *   is not a valid date.
 */
export function formatRelativeTime(
  value: string | Date,
  now: Date = new Date(),
  locale = 'en',
): string {
  const date = value instanceof Date ? value : new Date(value)
  const time = date.getTime()
  if (Number.isNaN(time)) {
    return ''
  }

  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  // Signed seconds: negative for the past, positive for the future.
  let delta = (time - now.getTime()) / 1000

  for (const division of RELATIVE_TIME_DIVISIONS) {
    if (Math.abs(delta) < division.amount) {
      return formatter.format(Math.round(delta), division.unit)
    }
    delta /= division.amount
  }

  return ''
}

/**
 * Returns today's date as a `yyyy-mm-dd` string, the value shape a native
 * `<input type="date">` expects. Shared by every form that defaults a date
 * field to today.
 *
 * Uses the viewer's **local** calendar date, not the UTC one. `toISOString()`
 * would report tomorrow for anyone east of UTC late in their day (and yesterday
 * for anyone far west early in theirs) — for a user in UTC+13 that is wrong for
 * 13 hours out of every 24, which silently anchored the summary view on the
 * wrong week or month.
 *
 * @returns Today's local date formatted as `yyyy-mm-dd`.
 */
export function todayIsoDate(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Formats a UTC instant for display in an explicit IANA timezone.
 *
 * Activities are shown in the timezone they were *recorded* in, so a ride at
 * 07:00 in Tokyo reads "07:00" to every viewer regardless of where they are.
 * Passing the real instant plus an explicit `timeZone` is what makes that true
 * by construction: the alternative — serving an offset-less local wall clock and
 * letting `new Date()` reinterpret it in the browser's zone — only produces the
 * right digits because two opposite conversions cancel, and that cancellation
 * breaks inside the viewer's DST spring-forward gap (a 01:30 activity renders as
 * 02:30) and yields a `Date` holding the wrong instant for any arithmetic.
 *
 * @param iso - The instant to format, as an ISO 8601 string carrying an offset.
 * @param timeZone - IANA timezone to render in. When `null`/omitted or invalid,
 *   falls back to the viewer's local timezone.
 * @param locale - BCP-47 locale tag controlling the output language.
 * @param options - `Intl.DateTimeFormat` options (e.g. `dateStyle`/`timeStyle`).
 * @returns The formatted string, or an empty string when `iso` is unparseable.
 */
export function formatZonedDateTime(
  iso: string | null | undefined,
  timeZone: string | null | undefined,
  locale: string,
  options: Intl.DateTimeFormatOptions,
): string {
  if (!iso) {
    return ''
  }
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  try {
    return new Intl.DateTimeFormat(locale, { ...options, timeZone: timeZone ?? undefined }).format(
      date,
    )
  } catch {
    // An unknown/garbage zone name makes Intl throw; showing the viewer's local
    // time is a better outcome than blanking the field.
    return new Intl.DateTimeFormat(locale, options).format(date)
  }
}

/**
 * Returns the configured first weekday on or before an ISO date.
 *
 * @param iso - Any `YYYY-MM-DD` date within the target week.
 * @param firstDayOfWeek - User's configured first weekday.
 * @returns The first date of the configured week as `YYYY-MM-DD`.
 */
export function weekStart(iso: string, firstDayOfWeek: Schemas['WeekDay']): string {
  const date = parseIsoDate(iso)
  const daysSinceWeekStart = (date.getUTCDay() - WEEKDAY_UTC_INDEX[firstDayOfWeek] + 7) % 7
  return toIsoDate(new Date(date.getTime() - daysSinceWeekStart * MS_PER_DAY))
}

/**
 * Returns the configured final weekday on or after an ISO date.
 *
 * @param iso - Any `YYYY-MM-DD` date within the target week.
 * @param firstDayOfWeek - User's configured first weekday.
 * @returns The final date of the configured week as `YYYY-MM-DD`.
 */
export function weekEnd(iso: string, firstDayOfWeek: Schemas['WeekDay']): string {
  const start = parseIsoDate(weekStart(iso, firstDayOfWeek))
  return toIsoDate(new Date(start.getTime() + 6 * MS_PER_DAY))
}

/**
 * Shifts an ISO date by whole weeks.
 *
 * @param iso - The `YYYY-MM-DD` date to shift.
 * @param delta - Number of weeks to add or subtract.
 * @returns The shifted date as `YYYY-MM-DD`.
 */
export function shiftWeeks(iso: string, delta: number): string {
  const date = parseIsoDate(iso)
  return toIsoDate(new Date(date.getTime() + delta * 7 * MS_PER_DAY))
}

/**
 * Formats an ISO timestamp as a localized medium-style date (e.g. "Jun 25,
 * 2026"), or an empty string when the value cannot be parsed. Shared by list
 * rows that show a creation, link, or last-used date without a time component.
 *
 * @param iso - The timestamp to format, as an ISO 8601 string.
 * @param locale - BCP-47 locale tag controlling the output language.
 * @returns The localized date, or an empty string when `iso` is not a valid date.
 */
export function formatMediumDate(iso: string, locale = 'en'): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? ''
    : new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(date)
}

/**
 * Formats an ISO timestamp as a localized medium-style date with a short time
 * (e.g. "Jun 25, 2026, 2:30 PM"), or an empty string when the value cannot be
 * parsed. Shared by session/device rows that show a precise last-seen instant.
 *
 * @param iso - The timestamp to format, as an ISO 8601 string.
 * @param locale - BCP-47 locale tag controlling the output language.
 * @returns The localized date-time, or an empty string when `iso` is not a valid date.
 */
export function formatMediumDateTime(iso: string, locale = 'en'): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? ''
    : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}
