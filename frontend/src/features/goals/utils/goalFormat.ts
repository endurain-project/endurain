import {
  Bike,
  Dumbbell,
  Footprints,
  HeartPulse,
  PersonStanding,
  Waves,
  type LucideIcon,
} from '@lucide/vue'

import type { Schemas } from '@/types'
import type { GoalActivityType, GoalInterval, GoalMetric } from '@/features/goals/types'

import { kmToMiles, milesToKm } from '@/utils/units'

/** Metres in one foot (exact), used for elevation conversions. */
const METERS_PER_FOOT = 0.3048

/** Seconds in one hour, used for duration conversions. */
const SECONDS_PER_HOUR = 3600

/** Seconds in one minute, used for duration conversions. */
const SECONDS_PER_MINUTE = 60

/** Rounds a value to at most two decimal places. */
function round2(value: number): number {
  return Math.round(value * 100) / 100
}

/**
 * Converts a stored distance in metres to the user's display unit.
 *
 * @param meters - Distance in metres.
 * @param units - The user's measurement system.
 * @returns The distance in km (metric) or miles (imperial), to two decimals.
 */
export function metersToDistanceValue(meters: number, units: Schemas['Units']): number {
  const km = meters / 1000
  return round2(units === 'imperial' ? kmToMiles(km) : km)
}

/**
 * Converts a display distance back to the backend's base unit (metres).
 *
 * @param value - Distance in the user's display unit (km or miles).
 * @param units - The user's measurement system.
 * @returns The distance in whole metres.
 */
export function distanceValueToMeters(value: number, units: Schemas['Units']): number {
  const km = units === 'imperial' ? milesToKm(value) : value
  return Math.round(km * 1000)
}

/**
 * Converts a stored elevation in metres to the user's display unit.
 *
 * @param meters - Elevation in metres.
 * @param units - The user's measurement system.
 * @returns The elevation in metres (metric) or feet (imperial), rounded whole.
 */
export function metersToElevationValue(meters: number, units: Schemas['Units']): number {
  const value = units === 'imperial' ? meters / METERS_PER_FOOT : meters
  return Math.round(value)
}

/**
 * Converts a display elevation back to the backend's base unit (metres).
 *
 * @param value - Elevation in the user's display unit (metres or feet).
 * @param units - The user's measurement system.
 * @returns The elevation in whole metres.
 */
export function elevationValueToMeters(value: number, units: Schemas['Units']): number {
  return Math.round(units === 'imperial' ? value * METERS_PER_FOOT : value)
}

/** An hours/minutes breakdown of a duration. */
export interface HoursMinutes {
  hours: number
  minutes: number
}

/**
 * Splits a duration in seconds into whole hours and minutes.
 *
 * @param seconds - Duration in seconds.
 * @returns The hours and (rounded) minutes components.
 */
export function secondsToHoursMinutes(seconds: number): HoursMinutes {
  const safe = Math.max(0, Math.floor(seconds))
  return {
    hours: Math.floor(safe / SECONDS_PER_HOUR),
    minutes: Math.round((safe % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE),
  }
}

/**
 * Combines hours and minutes into a total duration in seconds.
 *
 * @param hours - Whole hours.
 * @param minutes - Whole minutes.
 * @returns The total duration in seconds.
 */
export function hoursMinutesToSeconds(hours: number, minutes: number): number {
  return Math.max(
    0,
    Math.round(hours) * SECONDS_PER_HOUR + Math.round(minutes) * SECONDS_PER_MINUTE,
  )
}

/** Recurrence intervals in display order, shared by the goal form and filters. */
export const GOAL_INTERVALS: readonly GoalInterval[] = ['daily', 'weekly', 'monthly', 'yearly']

/** Activity types in display order, shared by the goal form and filters. */
export const GOAL_ACTIVITY_TYPES: readonly GoalActivityType[] = [
  'run',
  'bike',
  'swim',
  'walk',
  'strength',
  'cardio',
]

/** Goal metrics in display order, shared by the goal form and filters. */
export const GOAL_METRICS: readonly GoalMetric[] = [
  'calories',
  'activities',
  'distance',
  'elevation',
  'duration',
]

/** i18n label keys for each recurrence interval. */
export const INTERVAL_LABEL_KEYS: Record<GoalInterval, string> = {
  daily: 'settings.goals.interval.daily',
  weekly: 'settings.goals.interval.weekly',
  monthly: 'settings.goals.interval.monthly',
  yearly: 'settings.goals.interval.yearly',
}

/** i18n label keys for each activity type. */
export const ACTIVITY_TYPE_LABEL_KEYS: Record<GoalActivityType, string> = {
  run: 'settings.goals.activityType.run',
  bike: 'settings.goals.activityType.bike',
  swim: 'settings.goals.activityType.swim',
  walk: 'settings.goals.activityType.walk',
  strength: 'settings.goals.activityType.strength',
  cardio: 'settings.goals.activityType.cardio',
}

/** i18n label keys for each goal metric. */
export const GOAL_METRIC_LABEL_KEYS: Record<GoalMetric, string> = {
  calories: 'settings.goals.metric.calories',
  activities: 'settings.goals.metric.activities',
  distance: 'settings.goals.metric.distance',
  elevation: 'settings.goals.metric.elevation',
  duration: 'settings.goals.metric.duration',
}

/** Lucide icon for each activity type, shown on the goal row. */
export const ACTIVITY_TYPE_ICONS: Record<GoalActivityType, LucideIcon> = {
  run: Footprints,
  bike: Bike,
  swim: Waves,
  walk: PersonStanding,
  strength: Dumbbell,
  cardio: HeartPulse,
}
