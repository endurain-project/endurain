/**
 * Locale-aware number formatting for display. Every number a user reads goes through
 * {@link formatNumber} so separators and digits follow the app language rather than the browser's.
 * The locale comes from the shared i18n instance instead of a parameter: the display formatters
 * (distance, pace, steps, weight, summaries) are called from many computeds, tables and chart
 * callbacks, and reading `locale.value` inside them also makes the caller re-run when the language
 * changes. Values that are not for display (`<input type="number">` values, API payloads, exports)
 * must stay plain JS number strings and never pass through here.
 */

import i18n from '@/i18n'

/** Fraction-digit options accepted by {@link formatNumber}. */
export interface NumberFormatOptions {
  /** Fewest decimal places to show (default 0). */
  minimumFractionDigits?: number
  /** Most decimal places to show (default: the minimum, or 0). */
  maximumFractionDigits?: number
}

/** One `Intl.NumberFormat` per locale and options, since constructing one is comparatively slow. */
const formatters = new Map<string, Intl.NumberFormat>()

/**
 * The active app locale as a BCP-47 tag.
 *
 * @returns The i18n locale.
 */
export function numberLocale(): string {
  return i18n.global.locale.value
}

/**
 * Formats a number for display in the active app locale, with grouping.
 *
 * @param value - The number to format.
 * @param options - Fraction digits; omitted means a whole number.
 * @returns The localized number (`1,234.5` in English, `1.234,5` in German).
 */
export function formatNumber(value: number, options: NumberFormatOptions = {}): string {
  const locale = numberLocale()
  const minimumFractionDigits = options.minimumFractionDigits ?? options.maximumFractionDigits ?? 0
  const maximumFractionDigits = options.maximumFractionDigits ?? minimumFractionDigits
  const key = `${locale}|${minimumFractionDigits}|${maximumFractionDigits}`
  let formatter = formatters.get(key)
  if (!formatter) {
    formatter = new Intl.NumberFormat(locale, { minimumFractionDigits, maximumFractionDigits })
    formatters.set(key, formatter)
  }
  return formatter.format(value)
}

/**
 * Formats a number with a fixed count of decimal places (the display counterpart of `toFixed`).
 *
 * @param value - The number to format.
 * @param digits - Decimal places to always show.
 * @returns The localized number.
 */
export function formatFixed(value: number, digits: number): string {
  return formatNumber(value, { minimumFractionDigits: digits, maximumFractionDigits: digits })
}
