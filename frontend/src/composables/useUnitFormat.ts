import { useI18n } from 'vue-i18n'

import type { UnitKey } from '@/i18n'

/**
 * Localized rendering of measurement units, durations and percentages. Pure
 * formatters return a {@link UnitKey} next to the value; views resolve it here so
 * every unit symbol comes from the `units` namespace of the active locale.
 *
 * @returns The `unitLabel`, `withUnit`, `formatMetric`, `duration` and `percent` formatters.
 */
export function useUnitFormat() {
  const { t, locale } = useI18n()

  /**
   * Resolves a unit symbol in the active locale.
   *
   * @param unit - The unit key.
   * @returns The localized symbol (e.g. `km`).
   */
  function unitLabel(unit: UnitKey): string {
    return t(`units.${unit}`)
  }

  /**
   * Joins a formatted value and its unit as `value unit`.
   *
   * @param value - The formatted value.
   * @param unit - The unit key, or `null` for a unitless value.
   * @returns The combined string, or the bare value when there is no unit.
   */
  function withUnit(value: string, unit: UnitKey | null): string {
    return unit ? `${value} ${unitLabel(unit)}` : value
  }

  /**
   * Joins a formatter's split `{ value, unit }` result as `value unit`.
   *
   * @param metric - The formatted value and its unit key.
   * @returns The combined string, or the bare value when there is no unit.
   */
  function formatMetric(metric: { value: string; unit: UnitKey | null }): string {
    return withUnit(metric.value, metric.unit)
  }

  /**
   * Formats an hours-and-minutes duration (e.g. `8h 5m`).
   *
   * @param hours - Whole hours.
   * @param minutes - Remaining whole minutes.
   * @param showZeroHours - Keep the hours part when it is zero (`0h 5m` instead of `5m`).
   * @returns The localized duration.
   */
  function duration(hours: number, minutes: number, showZeroHours = false): string {
    return hours > 0 || showZeroHours
      ? t('units.duration.hoursMinutes', { hours, minutes })
      : t('units.duration.minutes', { minutes })
  }

  /**
   * Formats a percentage given on a 0–100 scale with the locale's percent style
   * (`50%`, `50 %`, `%50`).
   *
   * @param value - The percentage, 0–100.
   * @param fractionDigits - Decimal places to show.
   * @returns The localized percentage.
   */
  function percent(value: number, fractionDigits = 0): string {
    return new Intl.NumberFormat(locale.value, {
      style: 'percent',
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    }).format(value / 100)
  }

  return { unitLabel, withUnit, formatMetric, duration, percent }
}
