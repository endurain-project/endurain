import type { Schemas } from '@/types'

import { kmToMiles } from '@/utils/units'

import {
  activityTypeIsRowing,
  activityTypeIsRunning,
  activityTypeIsStandUpPaddling,
  activityTypeIsSwimming,
  activityTypeUsesKnots,
} from './activityType'

/** The user's unit system. */
export type Units = Schemas['Units']

/** Metres-per-second to kilometres-per-hour. */
const MS_TO_KMH = 3.6
/** Metres-per-second to miles-per-hour. */
const MS_TO_MPH = 2.23694
/** Metres-per-second to knots. */
const MS_TO_KNOTS = 1.94384
/** Metres in one mile. */
const METERS_PER_MILE = 1609.34
/** Metres in one yard. */
const METERS_PER_YARD = 0.9144
/** Metres to feet. */
const METERS_TO_FEET = 3.28084

/** A formatted metric split into its value and unit for the metric pills. */
export interface FormattedMetric {
  /** The formatted numeric value (no unit). */
  value: string
  /** The unit suffix (may be empty). */
  unit: string
}

/**
 * Combines a {@link FormattedMetric} into a single `value unit` string for
 * dense contexts (lap tables, tooltips).
 *
 * @param metric - The split metric.
 * @returns The combined string.
 */
export function combineMetric(metric: FormattedMetric): string {
  return metric.unit ? `${metric.value} ${metric.unit}` : metric.value
}

/**
 * Formats a duration as `H:MM:SS` (or `MM:SS` under an hour), mirroring v1's
 * `formatSecondsToHoursMinutesSeconds`.
 *
 * @param seconds - Duration in seconds.
 * @returns The clock-formatted duration, or `--` for missing input.
 */
export function formatHmsDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return '--'
  }
  const whole = Math.floor(seconds)
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const secs = whole % 60
  const mm = minutes.toString().padStart(2, '0')
  const ss = secs.toString().padStart(2, '0')
  if (hours > 0) {
    return `${hours}:${mm}:${ss}`
  }
  return `${mm}:${ss}`
}

/**
 * Formats `minutes:seconds` from a per-unit pace in seconds, rolling a rounded
 * 60 up to the next minute. Exported for chart tooltips/ticks that plot pace in
 * seconds and need a `M:SS` label.
 *
 * @param secondsPerUnit - Seconds for the pace's distance unit.
 * @returns The `M:SS` pace string.
 */
export function formatPaceClock(secondsPerUnit: number): string {
  let minutes = Math.floor(secondsPerUnit / 60)
  let seconds = Math.round(secondsPerUnit - minutes * 60)
  if (seconds === 60) {
    minutes += 1
    seconds = 0
  }
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

/**
 * Resolves the pace unit label for an activity type and unit system.
 *
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns The pace unit label (e.g. `min/km`).
 */
export function paceUnitLabel(activityType: number, units: Units): string {
  if (activityTypeIsSwimming(activityType)) {
    return units === 'imperial' ? 'min/100yd' : 'min/100m'
  }
  if (activityTypeIsRowing(activityType) || activityTypeIsStandUpPaddling(activityType)) {
    return 'min/500m'
  }
  return units === 'imperial' ? 'min/mi' : 'min/km'
}

/**
 * Converts a pace from seconds-per-metre into seconds for the activity's
 * display distance unit (km/mi for foot sports, 100m/100yd for swimming, 500m
 * for rowing/SUP).
 *
 * @param secondsPerMeter - Pace in seconds per metre.
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns Seconds for the display distance unit.
 */
export function paceToDisplaySeconds(
  secondsPerMeter: number,
  activityType: number,
  units: Units,
): number {
  if (activityTypeIsSwimming(activityType)) {
    return units === 'imperial' ? secondsPerMeter * 100 * METERS_PER_YARD : secondsPerMeter * 100
  }
  if (activityTypeIsRowing(activityType) || activityTypeIsStandUpPaddling(activityType)) {
    return secondsPerMeter * 500
  }
  return units === 'imperial' ? secondsPerMeter * METERS_PER_MILE : secondsPerMeter * 1000
}

/**
 * Formats a pace from seconds-per-metre into the unit appropriate for the
 * activity type, mirroring v1's pace formatters (running min/km·mi, swimming
 * min/100m·100yd, rowing/SUP min/500m).
 *
 * @param secondsPerMeter - Pace in seconds per metre.
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns The split pace metric.
 */
export function formatPace(
  secondsPerMeter: number | null | undefined,
  activityType: number,
  units: Units,
): FormattedMetric {
  const unit = paceUnitLabel(activityType, units)
  if (secondsPerMeter === null || secondsPerMeter === undefined || secondsPerMeter <= 0) {
    return { value: '--', unit }
  }
  return {
    value: formatPaceClock(paceToDisplaySeconds(secondsPerMeter, activityType, units)),
    unit,
  }
}

/**
 * Resolves the speed unit label, accounting for marine sports (knots).
 *
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns The speed unit label.
 */
export function speedUnitLabel(activityType: number, units: Units): string {
  if (activityTypeUsesKnots(activityType)) {
    return 'kn'
  }
  return units === 'imperial' ? 'mph' : 'km/h'
}

/**
 * Converts a speed from metres-per-second into the display unit's numeric
 * value, using knots for marine sports and otherwise the user's unit system.
 *
 * @param metersPerSecond - Speed in metres per second.
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns The converted speed value.
 */
export function speedToDisplay(
  metersPerSecond: number,
  activityType: number,
  units: Units,
): number {
  if (activityTypeUsesKnots(activityType)) {
    return metersPerSecond * MS_TO_KNOTS
  }
  return metersPerSecond * (units === 'imperial' ? MS_TO_MPH : MS_TO_KMH)
}

/**
 * Formats a speed from metres-per-second, using knots for marine sports and
 * otherwise the user's unit system.
 *
 * @param metersPerSecond - Speed in metres per second.
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns The split speed metric.
 */
export function formatSpeed(
  metersPerSecond: number | null | undefined,
  activityType: number,
  units: Units,
): FormattedMetric {
  const unit = speedUnitLabel(activityType, units)
  if (metersPerSecond === null || metersPerSecond === undefined || metersPerSecond < 0) {
    return { value: '--', unit }
  }
  return { value: speedToDisplay(metersPerSecond, activityType, units).toFixed(2), unit }
}

/**
 * Resolves the distance unit label, accounting for swimming (metres/yards).
 *
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns The distance unit label.
 */
export function distanceUnitLabel(activityType: number, units: Units): string {
  if (activityTypeIsSwimming(activityType)) {
    return units === 'imperial' ? 'yd' : 'm'
  }
  return units === 'imperial' ? 'mi' : 'km'
}

/**
 * Formats a distance from metres. Swimming is shown in metres/yards; other
 * sports in kilometres/miles.
 *
 * @param meters - Distance in metres.
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns The split distance metric.
 */
export function formatDistance(
  meters: number | null | undefined,
  activityType: number,
  units: Units,
): FormattedMetric {
  const unit = distanceUnitLabel(activityType, units)
  if (meters === null || meters === undefined || meters < 0) {
    return { value: '--', unit }
  }
  if (activityTypeIsSwimming(activityType)) {
    const value = units === 'imperial' ? meters / METERS_PER_YARD : meters
    return { value: Math.round(value).toString(), unit }
  }
  const km = meters / 1000
  const value = units === 'imperial' ? kmToMiles(km) : km
  return { value: value.toFixed(2), unit }
}

/**
 * Converts metres to feet.
 *
 * @param meters - Elevation in metres.
 * @returns The equivalent feet.
 */
export function metersToFeet(meters: number): number {
  return meters * METERS_TO_FEET
}

/**
 * Converts an elevation from metres into the display unit's numeric value.
 *
 * @param meters - Elevation in metres.
 * @param units - The user's unit system.
 * @returns The converted elevation value.
 */
export function elevationToDisplay(meters: number, units: Units): number {
  return units === 'imperial' ? metersToFeet(meters) : meters
}

/**
 * Formats an elevation from metres into metres or feet.
 *
 * @param meters - Elevation in metres.
 * @param units - The user's unit system.
 * @returns The split elevation metric.
 */
export function formatElevation(meters: number | null | undefined, units: Units): FormattedMetric {
  const unit = units === 'imperial' ? 'ft' : 'm'
  if (meters === null || meters === undefined) {
    return { value: '--', unit }
  }
  return { value: Math.round(elevationToDisplay(meters, units)).toString(), unit }
}

/**
 * Converts Celsius to Fahrenheit.
 *
 * @param celsius - Temperature in Celsius.
 * @returns The equivalent Fahrenheit.
 */
export function celsiusToFahrenheit(celsius: number): number {
  return (celsius * 9) / 5 + 32
}

/**
 * Converts a temperature from Celsius into the display unit's numeric value.
 *
 * @param celsius - Temperature in Celsius.
 * @param units - The user's unit system.
 * @returns The converted temperature value.
 */
export function temperatureToDisplay(celsius: number, units: Units): number {
  return units === 'imperial' ? celsiusToFahrenheit(celsius) : celsius
}

/**
 * Resolves the cadence unit label (SPM for running, RPM otherwise).
 *
 * @param activityType - Numeric activity type.
 * @returns The cadence unit label.
 */
export function cadenceUnitLabel(activityType: number): string {
  return activityTypeIsRunning(activityType) ? 'spm' : 'rpm'
}
