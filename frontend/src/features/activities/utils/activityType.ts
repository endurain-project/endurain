import {
  Activity as ActivityIcon,
  Bike,
  Dumbbell,
  Footprints,
  MountainSnow,
  Sailboat,
  Snowflake,
  Waves,
  Wind,
  type LucideIcon,
} from '@lucide/vue'

import type { GearType } from '@/features/gears/types'
import { GEAR_TYPE } from '@/features/gears/utils/gearType'

import type { ActivityBadgeType } from '@/components/ui/activity-type-badge'

import type { ActivityType } from '../types'

/**
 * Maps each backend activity type to its i18n label key under the
 * `activities.types` namespace. Mirrors v1's `activityLabelMap` so labels stay
 * consistent across the two frontends.
 */
export const ACTIVITY_TYPE_LABEL_KEYS: Record<ActivityType, string> = {
  run: 'activities.types.run',
  trail_run: 'activities.types.trailRun',
  virtual_run: 'activities.types.virtualRun',
  ride: 'activities.types.ride',
  gravel_ride: 'activities.types.gravelRide',
  mtb_ride: 'activities.types.mtbRide',
  virtual_ride: 'activities.types.virtualRide',
  lap_swimming: 'activities.types.lapSwimming',
  open_water_swimming: 'activities.types.openWaterSwimming',
  workout: 'activities.types.workout',
  walk: 'activities.types.walk',
  hike: 'activities.types.hike',
  rowing: 'activities.types.rowing',
  yoga: 'activities.types.yoga',
  alpine_ski: 'activities.types.alpineSki',
  nordic_ski: 'activities.types.nordicSki',
  snowboard: 'activities.types.snowboard',
  transition: 'activities.types.transition',
  strength_training: 'activities.types.strengthTraining',
  crossfit: 'activities.types.crossfit',
  tennis: 'activities.types.tennis',
  table_tennis: 'activities.types.tableTennis',
  badminton: 'activities.types.badminton',
  squash: 'activities.types.squash',
  racquetball: 'activities.types.racquetball',
  pickleball: 'activities.types.pickleball',
  commuting_ride: 'activities.types.commutingRide',
  indoor_ride: 'activities.types.indoorRide',
  mixed_surface_ride: 'activities.types.mixedSurfaceRide',
  windsurf: 'activities.types.windsurf',
  indoor_walk: 'activities.types.indoorWalk',
  stand_up_paddling: 'activities.types.standUpPaddling',
  surf: 'activities.types.surf',
  track_run: 'activities.types.trackRun',
  ebike_ride: 'activities.types.ebikeRide',
  ebike_mountain_ride: 'activities.types.ebikeMountainRide',
  ice_skate: 'activities.types.iceSkate',
  soccer: 'activities.types.soccer',
  padel: 'activities.types.padel',
  treadmill_run: 'activities.types.treadmillRun',
  cardio_training: 'activities.types.cardioTraining',
  kayaking: 'activities.types.kayaking',
  sailing: 'activities.types.sailing',
  snow_shoeing: 'activities.types.snowShoeing',
  inline_skating: 'activities.types.inlineSkating',
  hiit: 'activities.types.hiit',
  jump_rope: 'activities.types.jumpRope',
}

/**
 * Narrows a string to a backend activity type.
 *
 * @param value - Any string, such as a route query value.
 * @returns Whether the value is an activity type the backend knows.
 */
export function isActivityType(value: string): value is ActivityType {
  return Object.prototype.hasOwnProperty.call(ACTIVITY_TYPE_LABEL_KEYS, value)
}

const RUNNING_TYPES = new Set<ActivityType>([
  'run',
  'trail_run',
  'virtual_run',
  'track_run',
  'treadmill_run',
])
const CYCLING_TYPES = new Set<ActivityType>([
  'ride',
  'gravel_ride',
  'mtb_ride',
  'virtual_ride',
  'commuting_ride',
  'indoor_ride',
  'mixed_surface_ride',
  'ebike_ride',
  'ebike_mountain_ride',
])
const SWIMMING_TYPES = new Set<ActivityType>(['lap_swimming', 'open_water_swimming'])
// 44 (snowshoeing) is intentionally in both walking and snow groups, mirroring
// v1: it is paced like walking but uses snow gear.
const WALKING_TYPES = new Set<ActivityType>(['walk', 'hike', 'indoor_walk', 'snow_shoeing'])
const RACQUET_TYPES = new Set<ActivityType>([
  'tennis',
  'table_tennis',
  'badminton',
  'squash',
  'racquetball',
  'pickleball',
  'padel',
])
const ROWING_TYPES = new Set<ActivityType>(['rowing', 'kayaking'])
const SNOW_SKIING_TYPES = new Set<ActivityType>(['alpine_ski', 'nordic_ski', 'snow_shoeing'])

const SNOWBOARD_TYPE: ActivityType = 'snowboard'
const WINDSURF_TYPE: ActivityType = 'windsurf'
const SAILING_TYPE: ActivityType = 'sailing'
const STAND_UP_PADDLING_TYPE: ActivityType = 'stand_up_paddling'
const SURF_TYPE: ActivityType = 'surf'
const SKATING_TYPE: ActivityType = 'inline_skating'
const ICE_SKATING_TYPE: ActivityType = 'ice_skate'
const JUMP_ROPE_TYPE: ActivityType = 'jump_rope'
const VIRTUAL_TYPES = new Set<ActivityType>(['virtual_run', 'virtual_ride'])

/** @returns Whether the type is a running discipline. */
export function activityTypeIsRunning(type: ActivityType): boolean {
  return RUNNING_TYPES.has(type)
}

/** @returns Whether the type is a cycling discipline. */
export function activityTypeIsCycling(type: ActivityType): boolean {
  return CYCLING_TYPES.has(type)
}

/** @returns Whether the type is a swimming discipline. */
export function activityTypeIsSwimming(type: ActivityType): boolean {
  return SWIMMING_TYPES.has(type)
}

/** @returns Whether the type is a walking/hiking discipline. */
export function activityTypeIsWalking(type: ActivityType): boolean {
  return WALKING_TYPES.has(type)
}

/** @returns Whether the type is a racquet sport. */
export function activityTypeIsRacquet(type: ActivityType): boolean {
  return RACQUET_TYPES.has(type)
}

/** @returns Whether the type is a rowing/kayaking discipline. */
export function activityTypeIsRowing(type: ActivityType): boolean {
  return ROWING_TYPES.has(type)
}

/** @returns Whether the type is stand-up paddleboarding. */
export function activityTypeIsStandUpPaddling(type: ActivityType): boolean {
  return type === STAND_UP_PADDLING_TYPE
}

/** @returns Whether the type is sailing. */
export function activityTypeIsSailing(type: ActivityType): boolean {
  return type === SAILING_TYPE
}

/** @returns Whether the type is windsurfing. */
export function activityTypeIsWindsurf(type: ActivityType): boolean {
  return type === WINDSURF_TYPE
}

/** @returns Whether the type is surfing. */
export function activityTypeIsSurf(type: ActivityType): boolean {
  return type === SURF_TYPE
}

/** @returns Whether the type is snow skiing or snowshoeing. */
export function activityTypeIsSnowSkiing(type: ActivityType): boolean {
  return SNOW_SKIING_TYPES.has(type)
}

/** @returns Whether the type is snowboarding. */
export function activityTypeIsSnowboarding(type: ActivityType): boolean {
  return type === SNOWBOARD_TYPE
}

/** @returns Whether the type is inline skating. */
export function activityTypeIsSkating(type: ActivityType): boolean {
  return type === SKATING_TYPE
}

/** @returns Whether the type is ice skating. */
export function activityTypeIsIceSkating(type: ActivityType): boolean {
  return type === ICE_SKATING_TYPE
}

/** @returns Whether the type is jump rope (total cycles = total jumps). */
export function activityTypeIsJumpRope(type: ActivityType): boolean {
  return type === JUMP_ROPE_TYPE
}

/**
 * Resolves the i18n key for a lap's cycle-count column header. FIT stores a
 * generic `total_cycles`, but its real-world meaning is sport-specific:
 * strokes (rowing/paddling/swimming), pedal revolutions (cycling), strides
 * (running/walking — one cycle is a stride, i.e. two steps, not one step), or
 * jumps (jump rope). Falls back to the generic "cycles" label.
 *
 * @param type - The activity type.
 * @returns The i18n key under `activities.laps`.
 */
export function lapCyclesLabelKey(type: ActivityType): string {
  if (
    activityTypeIsRowing(type) ||
    activityTypeIsStandUpPaddling(type) ||
    activityTypeIsSwimming(type)
  ) {
    return 'activities.laps.strokes'
  }
  if (activityTypeIsCycling(type)) {
    return 'activities.laps.revolutions'
  }
  if (activityTypeIsRunning(type) || activityTypeIsWalking(type)) {
    return 'activities.laps.strides'
  }
  if (activityTypeIsJumpRope(type)) {
    return 'activities.laps.jumps'
  }
  return 'activities.laps.cycles'
}

/**
 * Maps an activity type to the gear type whose gears may be associated with it,
 * mirroring v1's `ActivityView.getGearsByActivityType`. Returns `null` for
 * activity families that have no associated gear (e.g. strength, cardio, HIIT).
 * Running/walking is checked before snow sports so snowshoeing (type 44, which
 * is in both groups) resolves to shoes, matching v1's branch order.
 *
 * @param type - The activity type.
 * @returns The gear type, or `null` when no gear applies.
 */
export function activityTypeToGearType(type: ActivityType): GearType | null {
  if (activityTypeIsCycling(type)) {
    return GEAR_TYPE.BICYCLE
  }
  if (activityTypeIsRunning(type) || activityTypeIsWalking(type)) {
    return GEAR_TYPE.SHOES
  }
  if (activityTypeIsSwimming(type)) {
    return GEAR_TYPE.WETSUIT
  }
  if (activityTypeIsRacquet(type)) {
    return GEAR_TYPE.RACQUET
  }
  if (activityTypeIsSnowSkiing(type)) {
    return GEAR_TYPE.SKIS
  }
  if (activityTypeIsSnowboarding(type)) {
    return GEAR_TYPE.SNOWBOARD
  }
  if (activityTypeIsWindsurf(type)) {
    return GEAR_TYPE.WINDSURF
  }
  if (activityTypeIsStandUpPaddling(type) || activityTypeIsSurf(type)) {
    return GEAR_TYPE.WATER_SPORTS_BOARD
  }
  return null
}

/** @returns Whether the type is a virtual run/ride (shows a "virtual" badge). */
export function activityTypeIsVirtual(type: ActivityType): boolean {
  return VIRTUAL_TYPES.has(type)
}

/**
 * Whether speed should be expressed in knots (marine sports), overriding the
 * user's metric/imperial preference, mirroring v1.
 *
 * @param type - The activity type.
 * @returns Whether knots apply.
 */
export function activityTypeUsesKnots(type: ActivityType): boolean {
  return activityTypeIsSailing(type) || activityTypeIsWindsurf(type)
}

/**
 * Whether the activity is primarily distance-paced (pace metric) rather than
 * speed-based, mirroring v1's pace-vs-speed split.
 *
 * @param type - The activity type.
 * @returns Whether pace (not speed) is the headline tempo metric.
 */
export function activityTypeUsesPace(type: ActivityType): boolean {
  return (
    activityTypeIsRunning(type) ||
    activityTypeIsWalking(type) ||
    activityTypeIsSwimming(type) ||
    activityTypeIsRowing(type) ||
    activityTypeIsStandUpPaddling(type)
  )
}

/**
 * Activity types with no meaningful distance (gym/structured/indoor sessions):
 * workout, yoga, transition, strength, crossfit, cardio, HIIT, jump rope.
 * Racquet sports are also non-distance (handled via {@link activityTypeIsRacquet}).
 */
const NON_DISTANCE_TYPES = new Set<ActivityType>([
  'workout',
  'yoga',
  'transition',
  'strength_training',
  'crossfit',
  'cardio_training',
  'hiit',
  'jump_rope',
])

/**
 * Whether an activity is distance-based (shows distance/pace/elevation) versus
 * a non-distance session (gym/strength/racquet), mirroring v1's summary split.
 *
 * @param type - The activity type.
 * @returns Whether the activity is distance-based.
 */
export function activityTypeIsDistanceBased(type: ActivityType): boolean {
  return !NON_DISTANCE_TYPES.has(type) && !activityTypeIsRacquet(type)
}

/**
 * Maps an activity type to one of the five badge colour categories the
 * {@link ActivityTypeBadge} primitive supports.
 *
 * @param type - The activity type.
 * @returns The badge colour category.
 */
export function activityBadgeCategory(type: ActivityType): ActivityBadgeType {
  if (activityTypeIsRunning(type)) {
    return 'running'
  }
  if (activityTypeIsCycling(type)) {
    return 'cycling'
  }
  if (activityTypeIsSwimming(type)) {
    return 'swimming'
  }
  if (activityTypeIsWalking(type)) {
    return 'hiking'
  }
  return 'other'
}

/**
 * Resolves the Lucide icon representing an activity type. Falls back to a
 * generic activity glyph for unmapped types.
 *
 * @param type - The activity type.
 * @returns The icon component.
 */
export function activityTypeIcon(type: ActivityType): LucideIcon {
  if (activityTypeIsRunning(type) || activityTypeIsWalking(type)) {
    return Footprints
  }
  if (activityTypeIsCycling(type)) {
    return Bike
  }
  if (
    activityTypeIsSwimming(type) ||
    activityTypeIsRowing(type) ||
    activityTypeIsStandUpPaddling(type) ||
    activityTypeIsSurf(type)
  ) {
    return Waves
  }
  if (activityTypeIsSailing(type)) {
    return Sailboat
  }
  if (activityTypeIsWindsurf(type)) {
    return Wind
  }
  if (activityTypeIsSnowSkiing(type)) {
    return MountainSnow
  }
  if (activityTypeIsSnowboarding(type)) {
    return Snowflake
  }
  if (activityTypeIsRacquet(type)) {
    return Dumbbell
  }
  return ActivityIcon
}

/** Presentation bundle for an activity type. */
export interface ActivityTypePresentation {
  /** i18n key for the localized type label. */
  labelKey: string
  /** Badge colour category. */
  badge: ActivityBadgeType
  /** Lucide icon component. */
  icon: LucideIcon
}

/**
 * Bundles the label key, badge category, and icon for an activity type so views
 * resolve all three from one call.
 *
 * @param type - The activity type.
 * @returns The presentation bundle.
 */
export function presentActivityType(type: ActivityType): ActivityTypePresentation {
  return {
    labelKey: ACTIVITY_TYPE_LABEL_KEYS[type] ?? 'activities.types.workout',
    badge: activityBadgeCategory(type),
    icon: activityTypeIcon(type),
  }
}

/**
 * Sorts activity types alphabetically by their translated label.
 *
 * @param codes - Activity types.
 * @param t - The vue-i18n translate function.
 * @param locale - The active locale, whose collation rules order the labels.
 * @returns A new array of the codes ordered by localized label.
 */
export function sortActivityTypesByLabel(
  types: readonly ActivityType[],
  t: (key: string) => string,
  locale: string,
): ActivityType[] {
  const collator = new Intl.Collator(locale)
  const labels = new Map(types.map((type) => [type, t(presentActivityType(type).labelKey)]))
  return [...types].sort((a, b) => collator.compare(labels.get(a)!, labels.get(b)!))
}
