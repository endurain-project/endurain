import type { ActivityLap } from '@/features/activities/types'

import { activityTypeIsSwimming } from '@/features/activities/utils/activityType'

/** The FIT `intensity` value marking a recovery lap. */
const REST_INTENSITY = 'rest'

/** A lap enriched with rest and relative-pace presentation data. */
export interface NormalizedLap {
  lap: ActivityLap
  /**
   * Whether this lap is a swim rest (zero/null distance). Two rests in a row are
   * treated as a drill rather than a rest, mirroring v1's heuristic. Kept
   * separate from {@link isRest} so swim-only behaviour stays explicit.
   */
  swimIsRest: boolean
  /**
   * Whether this lap is a recovery lap for presentation purposes: a FIT
   * `intensity === 'rest'` lap (any sport) or a swim rest. Rest laps are dimmed
   * and have their (meaningless) pace blanked in the table.
   */
  isRest: boolean
  /**
   * Pace relative to the fastest non-rest lap, clamped to 0–100 (100 = fastest).
   * `null` when the lap has no pace or is a rest, so a progress bar can be omitted.
   */
  normalizedScore: number | null
}

/** Aggregated totals over the active (non-rest) laps of an activity. */
export interface ActiveLapSummary {
  /** Summed distance of active laps, in metres. */
  totalDistance: number
  /** Summed elapsed time of active laps, in seconds. */
  totalElapsedTime: number
  /** Average speed across active laps (distance / time), in metres per second. */
  avgSpeed: number
  /** Average pace across active laps (time / distance), in seconds per metre. */
  avgPace: number
}

/**
 * Enriches laps with rest detection and a relative-pace score for the mini
 * progress bar. Pure (no formatting/i18n) so it is unit-testable; the table
 * component formats the underlying values.
 *
 * Rest laps (FIT `intensity === 'rest'` for any sport, or swim rests) are
 * excluded from the fastest-pace baseline and get a `null` score, because their
 * pace reflects idle drift rather than effort.
 *
 * @param laps - The activity's laps, in order.
 * @param activityType - Numeric activity-type code (for swim detection).
 * @returns The laps enriched with rest/score data, in the same order.
 */
export function normalizeLaps(laps: ActivityLap[], activityType: number): NormalizedLap[] {
  if (laps.length === 0) {
    return []
  }

  const isSwimming = activityTypeIsSwimming(activityType)

  const entries: NormalizedLap[] = laps.map((lap) => ({
    lap,
    swimIsRest: isSwimming && (lap.totalDistance === null || lap.totalDistance === 0),
    isRest: lap.intensity === REST_INTENSITY,
    normalizedScore: null,
  }))

  // Two rests in a row almost always means a drill set, not a real rest.
  for (let i = 0; i < entries.length - 1; i += 1) {
    const current = entries[i]
    const next = entries[i + 1]
    if (current && next && current.swimIsRest && next.swimIsRest) {
      next.swimIsRest = false
    }
  }

  // A lap is a rest for presentation if the device flagged it or it is a swim rest.
  for (const entry of entries) {
    entry.isRest = entry.isRest || entry.swimIsRest
  }

  // Baseline the pace bar against the fastest active lap only, so rest laps
  // (idle drift, huge pace) do not skew the scale.
  const paces = entries
    .filter((entry) => !entry.isRest)
    .map((entry) => entry.lap.enhancedAvgPace)
    .filter((pace): pace is number => pace !== null && pace > 0)
  const fastestPace = paces.length > 0 ? Math.min(...paces) : null

  for (const entry of entries) {
    const pace = entry.lap.enhancedAvgPace
    if (!entry.isRest && fastestPace !== null && pace !== null && pace > 0) {
      entry.normalizedScore = Math.min(Math.max((fastestPace / pace) * 100, 0), 100)
    }
  }

  return entries
}

/**
 * Aggregates the active (non-rest) laps into distance/time/pace totals for an
 * "active total" summary line. Pure so it is unit-testable.
 *
 * @param laps - The activity's laps, in order.
 * @param activityType - Numeric activity-type code (for swim detection).
 * @returns The active totals, or `null` when there is no usable active
 *   distance and time (e.g. no rest laps to separate, or missing data).
 */
export function summarizeActiveLaps(
  laps: ActivityLap[],
  activityType: number,
): ActiveLapSummary | null {
  let totalDistance = 0
  let totalElapsedTime = 0

  for (const entry of normalizeLaps(laps, activityType)) {
    if (entry.isRest) {
      continue
    }
    if (entry.lap.totalDistance !== null) {
      totalDistance += entry.lap.totalDistance
    }
    if (entry.lap.totalElapsedTime !== null) {
      totalElapsedTime += entry.lap.totalElapsedTime
    }
  }

  if (totalDistance <= 0 || totalElapsedTime <= 0) {
    return null
  }

  const avgSpeed = totalDistance / totalElapsedTime
  return {
    totalDistance,
    totalElapsedTime,
    avgSpeed,
    avgPace: 1 / avgSpeed,
  }
}
