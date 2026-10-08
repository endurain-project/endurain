import type { MetricPillVariants } from '@/components/ui/metric-pill'

import type { Activity } from '../types'
import {
  activityTypeIsCycling,
  activityTypeIsDistanceBased,
  activityTypeIsJumpRope,
  activityTypeIsRunning,
  activityTypeIsSailing,
  activityTypeIsWindsurf,
  activityTypeUsesPace,
} from './activityType'
import {
  combineMetric,
  formatDistance,
  formatElevation,
  formatHmsDuration,
  formatPace,
  formatSpeed,
  type Units,
} from './format'

/** Which privacy-gated metrics the current viewer is allowed to see. */
export interface MetricVisibility {
  pace: boolean
  speed: boolean
  hr: boolean
  power: boolean
  cadence: boolean
  elevation: boolean
}

/** A single summary metric tile. */
export interface MetricTile {
  /** Stable key for list rendering. */
  key: string
  /** i18n label key. */
  labelKey: string
  /** Formatted value. */
  value: string
  /** Unit suffix (may be empty). */
  unit: string
  /** Semantic colour accent for the value. */
  accent: NonNullable<MetricPillVariants['accent']>
}

/** Whether a numeric metric is present and finite. */
function has(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && Number.isFinite(value)
}

/**
 * Builds the curated summary metric tiles for an activity, mirroring v1: at most
 * six type-specific stats for distance-based activities, and just calories/time/
 * avg-HR for non-distance sessions (gym/strength/racquet). Privacy-hidden stats
 * are omitted for the current viewer.
 *
 * @param activity - The activity domain model.
 * @param units - The user's unit system.
 * @param visibility - Which privacy-gated metrics the viewer may see.
 * @returns The ordered tiles to render (≤ 6 for distance activities, 3 otherwise).
 */
export function buildActivityMetrics(
  activity: Activity,
  units: Units,
  visibility: MetricVisibility,
): MetricTile[] {
  const type = activity.activityType
  const tiles: MetricTile[] = []

  // Summary "Time" uses moving (timer) time to match the source app (e.g.
  // Garmin) and the activity list; falls back to elapsed time when the device
  // did not record a separate timer time.
  const pushTime = (): void => {
    const duration = activity.totalTimerTime ?? activity.totalElapsedTime
    if (has(duration)) {
      tiles.push({
        key: 'time',
        labelKey: 'activities.metrics.time',
        value: formatHmsDuration(duration),
        unit: '',
        accent: 'ink',
      })
    }
  }
  const pushCalories = (): void => {
    if (has(activity.calories)) {
      tiles.push({
        key: 'calories',
        labelKey: 'activities.metrics.calories',
        value: String(Math.round(activity.calories)),
        unit: 'kcal',
        accent: 'effort',
      })
    }
  }
  const pushPace = (): void => {
    if (visibility.pace && has(activity.pace)) {
      const pace = formatPace(activity.pace, type, units)
      tiles.push({
        key: 'pace',
        labelKey: 'activities.metrics.avgPace',
        value: pace.value,
        unit: pace.unit,
        accent: 'info',
      })
    }
  }
  const pushAvgSpeed = (): void => {
    if (visibility.speed && has(activity.averageSpeed)) {
      const speed = formatSpeed(activity.averageSpeed, type, units)
      tiles.push({
        key: 'avgSpeed',
        labelKey: 'activities.metrics.avgSpeed',
        value: speed.value,
        unit: speed.unit,
        accent: 'info',
      })
    }
  }
  const pushElevationGain = (): void => {
    if (visibility.elevation && has(activity.elevationGain)) {
      const gain = formatElevation(activity.elevationGain, units)
      tiles.push({
        key: 'elevationGain',
        labelKey: 'activities.metrics.elevationGain',
        value: gain.value,
        unit: gain.unit,
        accent: 'goal',
      })
    }
  }
  const pushAvgPower = (): void => {
    if (visibility.power && has(activity.averagePower)) {
      tiles.push({
        key: 'avgPower',
        labelKey: 'activities.metrics.avgPower',
        value: String(Math.round(activity.averagePower)),
        unit: 'W',
        accent: 'effort',
      })
    }
  }
  const pushAvgHr = (): void => {
    if (visibility.hr && has(activity.averageHr)) {
      tiles.push({
        key: 'avgHr',
        labelKey: 'activities.metrics.avgHr',
        value: String(Math.round(activity.averageHr)),
        unit: 'bpm',
        accent: 'hr',
      })
    }
  }
  const pushMaxHr = (): void => {
    if (visibility.hr && has(activity.maxHr)) {
      tiles.push({
        key: 'maxHr',
        labelKey: 'activities.metrics.maxHr',
        value: String(Math.round(activity.maxHr)),
        unit: 'bpm',
        accent: 'hr',
      })
    }
  }
  // Jump rope: total_cycles is the total jump count and the headline metric
  // (jump rope has no distance). Other sports interpret cycles differently
  // (strides/pedal revolutions/strokes) where cadence already covers it.
  const pushJumps = (): void => {
    if (activityTypeIsJumpRope(type) && has(activity.totalCycles)) {
      tiles.push({
        key: 'jumps',
        labelKey: 'activities.metrics.jumps',
        value: String(Math.round(activity.totalCycles)),
        unit: '',
        accent: 'brand',
      })
    }
  }

  // Non-distance sessions (gym/strength/yoga/racquet/…): calories, time, avg HR.
  if (!activityTypeIsDistanceBased(type)) {
    pushJumps()
    pushCalories()
    pushTime()
    pushAvgHr()
    return tiles
  }

  // Distance-based: up to six type-curated stats, starting with distance + time.
  const distance = formatDistance(activity.distance, type, units)
  tiles.push({
    key: 'distance',
    labelKey: 'activities.metrics.distance',
    value: distance.value,
    unit: distance.unit,
    accent: 'brand',
  })
  pushTime()

  if (activityTypeIsCycling(type)) {
    // distance, time, elevation gain, avg power, avg speed, calories
    pushElevationGain()
    pushAvgPower()
    pushAvgSpeed()
    pushCalories()
  } else if (activityTypeIsRunning(type)) {
    // distance, time, pace, avg power, elevation gain, calories
    pushPace()
    pushAvgPower()
    pushElevationGain()
    pushCalories()
  } else if (activityTypeIsWindsurf(type) || activityTypeIsSailing(type)) {
    // distance, time, avg speed, avg HR, max HR, calories
    pushAvgSpeed()
    pushAvgHr()
    pushMaxHr()
    pushCalories()
  } else {
    // swimming/walking/hiking/rowing/…: distance, time, pace, avg HR, max HR, calories
    pushPace()
    pushAvgHr()
    pushMaxHr()
    pushCalories()
  }

  return tiles
}

/**
 * Formats a single lap's pace or speed for the laps table, choosing pace vs.
 * speed by activity type.
 *
 * @param enhancedAvgPace - Lap average pace in seconds per metre.
 * @param enhancedAvgSpeed - Lap average speed in metres per second.
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns A combined `value unit` string, or `--`.
 */
export function formatLapTempo(
  enhancedAvgPace: number | null,
  enhancedAvgSpeed: number | null,
  activityType: number,
  units: Units,
): string {
  if (activityTypeUsesPace(activityType)) {
    return enhancedAvgPace === null
      ? '--'
      : combineMetric(formatPace(enhancedAvgPace, activityType, units))
  }
  return enhancedAvgSpeed === null
    ? '--'
    : combineMetric(formatSpeed(enhancedAvgSpeed, activityType, units))
}
