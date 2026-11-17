import type { LucideIcon } from '@lucide/vue'

import type {
  ActivitySportKey,
  ActivitySportStats,
  ActivityStats,
  ActivityType,
} from '@/features/activities/types'
import { activityTypeIcon } from '@/features/activities/utils/activityType'

/** The metric a user can rank their sport stats by on the home dashboard. */
export type StatMetric = 'distance' | 'time' | 'calories'

/**
 * Maps each stats sport key to a representative activity type. The
 * representative type drives both the icon ({@link activityTypeIcon}) and the
 * unit-aware distance formatting (`formatDistance` special-cases swimming), so
 * the home stats reuse the exact presentation logic the rest of the app uses.
 */
const SPORT_ACTIVITY_TYPE: Record<ActivitySportKey, ActivityType> = {
  run: 'run',
  bike: 'ride',
  swim: 'lap_swimming',
  walk: 'walk',
  hike: 'hike',
  rowing: 'rowing',
  snow_ski: 'alpine_ski',
  snowboard: 'snowboard',
  windsurf: 'windsurf',
  stand_up_paddling: 'stand_up_paddling',
  surf: 'surf',
  kayaking: 'kayaking',
  sailing: 'sailing',
  snow_shoeing: 'snow_shoeing',
  inline_skating: 'inline_skating',
  other: 'workout',
}

/** The sport keys in their canonical display order. */
const SPORT_ORDER = Object.keys(SPORT_ACTIVITY_TYPE) as ActivitySportKey[]

/** One sport's row in the distance-stats list. */
export interface SportStatRow {
  /** The sport key (also the i18n suffix under `home.sports.*`). */
  key: ActivitySportKey
  /** The representative activity type, for unit-aware formatting. */
  activityType: ActivityType
  /** The Lucide icon representing the sport. */
  icon: LucideIcon
  /** i18n key for the sport's label. */
  labelKey: string
  /** The aggregated distance / time / calories for the sport. */
  stats: ActivitySportStats
}

/** Reads a metric's numeric value from a sport's stats. */
function metricValue(stats: ActivitySportStats, metric: StatMetric): number {
  return stats[metric] ?? 0
}

/**
 * Selects the top sports for a timeframe, ranked by the chosen metric. Sports
 * with a zero value for that metric are dropped (mirroring v1, which only lists
 * sports with activity), and the result is capped at `limit` rows.
 *
 * @param stats - The per-sport stats for the timeframe, or `undefined`.
 * @param metric - The metric to rank and display by.
 * @param limit - Maximum number of rows to return (defaults to 3).
 * @returns The ranked sport rows.
 */
export function topSports(
  stats: ActivityStats | undefined,
  metric: StatMetric,
  limit = 3,
): SportStatRow[] {
  if (!stats) {
    return []
  }
  return SPORT_ORDER.flatMap((key) => {
    const sportStats = stats[key]
    if (!sportStats || metricValue(sportStats, metric) <= 0) {
      return []
    }
    const activityType = SPORT_ACTIVITY_TYPE[key]
    return [
      {
        key,
        activityType,
        icon: activityTypeIcon(activityType),
        labelKey: `home.sports.${key}`,
        stats: sportStats,
      },
    ]
  })
    .sort((a, b) => metricValue(b.stats, metric) - metricValue(a.stats, metric))
    .slice(0, limit)
}
