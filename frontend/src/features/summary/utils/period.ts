/**
 * Calendar period math for the summary view. Every function works on date-only
 * strings (`YYYY-MM-DD`) or month strings (`YYYY-MM`) and computes purely
 * calendrical results in UTC, so the output never drifts with the viewer's
 * timezone (the classic `new Date('YYYY-MM-DD')` off-by-one trap).
 *
 * Period ranges return an **inclusive** end date to match the activities list
 * endpoint, whose date filter is `date(start_time) BETWEEN start AND end`
 * inclusive on both bounds. Week boundaries use the viewer's configured first
 * day of the week.
 */

import { shiftWeeks, todayIsoDate, weekEnd, weekStart } from '@/utils/datetime'

export { shiftWeeks, weekEnd, weekStart }

/** An inclusive `[startDate, endDate]` range as `YYYY-MM-DD` strings. */
export interface PeriodRange {
  /** Inclusive first day of the period. */
  startDate: string
  /** Inclusive last day of the period. */
  endDate: string
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

/** Parses a `YYYY-MM` string into its numeric year and 1-based month. */
function parseMonth(month: string): { year: number; month: number } {
  const parts = month.split('-')
  return { year: Number(parts[0]), month: Number(parts[1] ?? 1) }
}

/** Today's date as `YYYY-MM-DD` (the default week anchor). */
export function currentWeekAnchor(): string {
  return todayIsoDate()
}

/** The current month as `YYYY-MM` (the default month anchor). */
export function currentMonth(): string {
  return todayIsoDate().slice(0, 7)
}

/** The current calendar year (the default year anchor). */
export function currentYear(): number {
  return Number(todayIsoDate().slice(0, 4))
}

/**
 * The first day of the given month.
 *
 * @param month - The target month as `YYYY-MM`.
 * @returns The first day as `YYYY-MM-DD`.
 */
export function monthStart(month: string): string {
  const { year, month: monthNumber } = parseMonth(month)
  return `${year}-${String(monthNumber).padStart(2, '0')}-01`
}

/**
 * The last day of the given month (inclusive).
 *
 * @param month - The target month as `YYYY-MM`.
 * @returns The last day as `YYYY-MM-DD`.
 */
export function monthEnd(month: string): string {
  const { year, month: monthNumber } = parseMonth(month)
  // Day 0 of the next month rolls back to the last day of this month.
  return toIsoDate(new Date(Date.UTC(year, monthNumber, 0)))
}

/**
 * Shifts a month by whole months, rolling over years as needed.
 *
 * @param month - The `YYYY-MM` anchor month.
 * @param delta - Number of months to add (negative to subtract).
 * @returns The shifted month as `YYYY-MM`.
 */
export function shiftMonths(month: string, delta: number): string {
  const { year, month: monthNumber } = parseMonth(month)
  const shifted = new Date(Date.UTC(year, monthNumber - 1 + delta, 1))
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, '0')}`
}

/**
 * The inclusive date range spanning a calendar year.
 *
 * @param year - The target calendar year.
 * @returns The `Jan 1 … Dec 31` range as `YYYY-MM-DD` strings.
 */
export function yearRange(year: number): PeriodRange {
  return { startDate: `${year}-01-01`, endDate: `${year}-12-31` }
}

/**
 * Formats a date-only string as a localized medium date, pinned to UTC so the
 * day never shifts with the viewer's timezone.
 *
 * @param iso - The `YYYY-MM-DD` date.
 * @param locale - BCP-47 locale tag.
 * @returns The localized medium-style date (e.g. "Jun 15, 2026").
 */
export function formatPeriodDate(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(
    parseIsoDate(iso),
  )
}

/**
 * Formats a date-only string as a localized "month year" label, pinned to UTC.
 *
 * @param iso - Any `YYYY-MM-DD` date within the target month.
 * @param locale - BCP-47 locale tag.
 * @returns The localized label (e.g. "June 2026").
 */
export function monthLabel(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parseIsoDate(iso))
}

/**
 * The localized full weekday name for a Monday-based day index.
 *
 * @param dayIndex - `0` = Monday … `6` = Sunday.
 * @param locale - BCP-47 locale tag.
 * @returns The localized weekday name (e.g. "Monday").
 */
export function weekdayLabel(dayIndex: number, locale: string): string {
  // 2024-01-01 is a Monday; add the index to land on the right weekday.
  const date = new Date(Date.UTC(2024, 0, 1 + dayIndex))
  return new Intl.DateTimeFormat(locale, { weekday: 'long', timeZone: 'UTC' }).format(date)
}

/**
 * The localized full month name for a 1-based month number.
 *
 * @param monthNumber - `1` = January … `12` = December.
 * @param locale - BCP-47 locale tag.
 * @returns The localized month name (e.g. "January").
 */
export function monthNameLabel(monthNumber: number, locale: string): string {
  const date = new Date(Date.UTC(2024, monthNumber - 1, 1))
  return new Intl.DateTimeFormat(locale, { month: 'long', timeZone: 'UTC' }).format(date)
}
