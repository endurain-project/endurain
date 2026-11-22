/**
 * Client-side sub-type filters for the search view. Mirrors the v1 search page's
 * activity-category and gear-type dropdowns, but built on v2's shared,
 * unit-tested `activityType` predicates so the groupings stay in lock-step with
 * the rest of the app. Kept as pure functions (no Vue, no i18n) so they are
 * trivial to test and reuse.
 */

import type { ActivityType } from '@/features/activities/types'
import type { GearType } from '@/features/gears/types'

import {
  activityTypeIsCycling,
  activityTypeIsIceSkating,
  activityTypeIsRacquet,
  activityTypeIsRowing,
  activityTypeIsRunning,
  activityTypeIsSailing,
  activityTypeIsSkating,
  activityTypeIsSnowboarding,
  activityTypeIsSnowSkiing,
  activityTypeIsStandUpPaddling,
  activityTypeIsSurf,
  activityTypeIsSwimming,
  activityTypeIsWalking,
  activityTypeIsWindsurf,
} from '@/features/activities/utils/activityType'

/** Sentinel category meaning "no activity filter" (show every type). */
export const ALL_ACTIVITY_CATEGORIES = 'all'

/** Sentinel gear type meaning "no gear filter" (show every gear type). */
export const ALL_GEAR_TYPES = 'all'

/**
 * A selectable activity-discipline filter for the search view: a stable `value`
 * (also the i18n label leaf under `search.activityCategories`) and a predicate
 * over the activity type. Built on the shared `activityType` predicates
 * so the families stay consistent with the rest of the app.
 *
 * @property value - Stable identifier and i18n label leaf.
 * @property matches - Predicate deciding whether an activity type belongs.
 */
export interface ActivityCategoryFilter {
  value: string
  matches: (activityType: ActivityType) => boolean
}

/**
 * Activity-discipline filters, in display order (excluding the "all" option).
 * Grouped into families rather than exposing all 46 raw types: the niche/gym
 * types remain reachable via the unfiltered "all" option.
 */
export const ACTIVITY_CATEGORY_FILTERS: readonly ActivityCategoryFilter[] = [
  { value: 'running', matches: activityTypeIsRunning },
  { value: 'cycling', matches: activityTypeIsCycling },
  { value: 'swimming', matches: activityTypeIsSwimming },
  { value: 'walking', matches: activityTypeIsWalking },
  { value: 'racquet', matches: activityTypeIsRacquet },
  { value: 'rowing', matches: activityTypeIsRowing },
  {
    value: 'winterSports',
    matches: (type) =>
      activityTypeIsSnowSkiing(type) ||
      activityTypeIsSnowboarding(type) ||
      activityTypeIsIceSkating(type),
  },
  {
    value: 'waterSports',
    matches: (type) =>
      activityTypeIsWindsurf(type) ||
      activityTypeIsSailing(type) ||
      activityTypeIsStandUpPaddling(type) ||
      activityTypeIsSurf(type),
  },
  { value: 'skating', matches: activityTypeIsSkating },
]

/** Category lookup by `value`, built once for O(1) filtering. */
const CATEGORY_BY_VALUE = new Map(ACTIVITY_CATEGORY_FILTERS.map((filter) => [filter.value, filter]))

/**
 * Narrows activities to the chosen discipline category. The {@link
 * ALL_ACTIVITY_CATEGORIES} sentinel (or any unknown value) returns a copy of the
 * list unfiltered.
 *
 * @param activities - The activities to filter.
 * @param category - The selected category value.
 * @returns A new array of the activities matching the category.
 */
export function filterActivitiesByCategory<T extends { activityType: ActivityType }>(
  activities: readonly T[],
  category: string,
): T[] {
  const filter = CATEGORY_BY_VALUE.get(category)
  if (!filter) {
    return activities.slice()
  }
  return activities.filter((activity) => filter.matches(activity.activityType))
}

/**
 * Narrows gears to a single gear type. The {@link ALL_GEAR_TYPES} sentinel
 * returns a copy of the list unfiltered.
 *
 * @param gears - The gears to filter.
 * @param gearType - The selected gear type, or {@link ALL_GEAR_TYPES}.
 * @returns A new array of the gears of the chosen type.
 */
export function filterGearsByType<T extends { gearType: GearType }>(
  gears: readonly T[],
  gearType: GearType | typeof ALL_GEAR_TYPES,
): T[] {
  if (gearType === ALL_GEAR_TYPES) {
    return gears.slice()
  }
  return gears.filter((gear) => gear.gearType === gearType)
}
