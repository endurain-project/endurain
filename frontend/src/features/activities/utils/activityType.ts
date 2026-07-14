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

import { GEAR_TYPE } from '@/features/gears/utils/gearType'

import type { ActivityBadgeType } from '@/components/ui/activity-type-badge'

/**
 * Maps each backend activity-type code to its i18n label key under the
 * `activities.types` namespace. Mirrors v1's `activityLabelMap` so labels stay
 * consistent across the two frontends.
 */
export const ACTIVITY_TYPE_LABEL_KEYS: Record<number, string> = {
  1: 'activities.types.run',
  2: 'activities.types.trailRun',
  3: 'activities.types.virtualRun',
  4: 'activities.types.ride',
  5: 'activities.types.gravelRide',
  6: 'activities.types.mtbRide',
  7: 'activities.types.virtualRide',
  8: 'activities.types.lapSwimming',
  9: 'activities.types.openWaterSwimming',
  10: 'activities.types.workout',
  11: 'activities.types.walk',
  12: 'activities.types.hike',
  13: 'activities.types.rowing',
  14: 'activities.types.yoga',
  15: 'activities.types.alpineSki',
  16: 'activities.types.nordicSki',
  17: 'activities.types.snowboard',
  18: 'activities.types.transition',
  19: 'activities.types.strengthTraining',
  20: 'activities.types.crossfit',
  21: 'activities.types.tennis',
  22: 'activities.types.tableTennis',
  23: 'activities.types.badminton',
  24: 'activities.types.squash',
  25: 'activities.types.racquetball',
  26: 'activities.types.pickleball',
  27: 'activities.types.commutingRide',
  28: 'activities.types.indoorRide',
  29: 'activities.types.mixedSurfaceRide',
  30: 'activities.types.windsurf',
  31: 'activities.types.indoorWalk',
  32: 'activities.types.standUpPaddling',
  33: 'activities.types.surf',
  34: 'activities.types.trackRun',
  35: 'activities.types.ebikeRide',
  36: 'activities.types.ebikeMountainRide',
  37: 'activities.types.iceSkate',
  38: 'activities.types.soccer',
  39: 'activities.types.padel',
  40: 'activities.types.treadmillRun',
  41: 'activities.types.cardioTraining',
  42: 'activities.types.kayaking',
  43: 'activities.types.sailing',
  44: 'activities.types.snowShoeing',
  45: 'activities.types.inlineSkating',
  46: 'activities.types.hiit',
  47: 'activities.types.jumpRope',
}

const RUNNING_TYPES = new Set([1, 2, 3, 34, 40])
const CYCLING_TYPES = new Set([4, 5, 6, 7, 27, 28, 29, 35, 36])
const SWIMMING_TYPES = new Set([8, 9])
// 44 (snowshoeing) is intentionally in both walking and snow groups, mirroring
// v1: it is paced like walking but uses snow gear.
const WALKING_TYPES = new Set([11, 12, 31, 44])
const RACQUET_TYPES = new Set([21, 22, 23, 24, 25, 26, 39])
const ROWING_TYPES = new Set([13, 42])
const SNOW_SKIING_TYPES = new Set([15, 16, 44])

const SWIMMING_TYPE = SWIMMING_TYPES
const SNOWBOARD_TYPE = 17
const WINDSURF_TYPE = 30
const SAILING_TYPE = 43
const STAND_UP_PADDLING_TYPE = 32
const SURF_TYPE = 33
const SKATING_TYPE = 45
const ICE_SKATING_TYPE = 37
const JUMP_ROPE_TYPE = 47
const VIRTUAL_TYPES = new Set([3, 7])

/** @returns Whether the type is a running discipline. */
export function activityTypeIsRunning(type: number): boolean {
  return RUNNING_TYPES.has(type)
}

/** @returns Whether the type is a cycling discipline. */
export function activityTypeIsCycling(type: number): boolean {
  return CYCLING_TYPES.has(type)
}

/** @returns Whether the type is a swimming discipline. */
export function activityTypeIsSwimming(type: number): boolean {
  return SWIMMING_TYPE.has(type)
}

/** @returns Whether the type is a walking/hiking discipline. */
export function activityTypeIsWalking(type: number): boolean {
  return WALKING_TYPES.has(type)
}

/** @returns Whether the type is a racquet sport. */
export function activityTypeIsRacquet(type: number): boolean {
  return RACQUET_TYPES.has(type)
}

/** @returns Whether the type is a rowing/kayaking discipline. */
export function activityTypeIsRowing(type: number): boolean {
  return ROWING_TYPES.has(type)
}

/** @returns Whether the type is stand-up paddleboarding. */
export function activityTypeIsStandUpPaddling(type: number): boolean {
  return type === STAND_UP_PADDLING_TYPE
}

/** @returns Whether the type is sailing. */
export function activityTypeIsSailing(type: number): boolean {
  return type === SAILING_TYPE
}

/** @returns Whether the type is windsurfing. */
export function activityTypeIsWindsurf(type: number): boolean {
  return type === WINDSURF_TYPE
}

/** @returns Whether the type is surfing. */
export function activityTypeIsSurf(type: number): boolean {
  return type === SURF_TYPE
}

/** @returns Whether the type is snow skiing or snowshoeing. */
export function activityTypeIsSnowSkiing(type: number): boolean {
  return SNOW_SKIING_TYPES.has(type)
}

/** @returns Whether the type is snowboarding. */
export function activityTypeIsSnowboarding(type: number): boolean {
  return type === SNOWBOARD_TYPE
}

/** @returns Whether the type is inline skating. */
export function activityTypeIsSkating(type: number): boolean {
  return type === SKATING_TYPE
}

/** @returns Whether the type is ice skating. */
export function activityTypeIsIceSkating(type: number): boolean {
  return type === ICE_SKATING_TYPE
}

/** @returns Whether the type is jump rope (total cycles = total jumps). */
export function activityTypeIsJumpRope(type: number): boolean {
  return type === JUMP_ROPE_TYPE
}

/**
 * Resolves the i18n key for a lap's cycle-count column header. FIT stores a
 * generic `total_cycles`, but its real-world meaning is sport-specific:
 * strokes (rowing/paddling/swimming), pedal revolutions (cycling), strides
 * (running/walking — one cycle is a stride, i.e. two steps, not one step), or
 * jumps (jump rope). Falls back to the generic "cycles" label.
 *
 * @param type - Numeric activity-type code.
 * @returns The i18n key under `activities.laps`.
 */
export function lapCyclesLabelKey(type: number): string {
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
 * @param type - Numeric activity-type code.
 * @returns The numeric gear type, or `null` when no gear applies.
 */
export function activityTypeToGearType(type: number): number | null {
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
export function activityTypeIsVirtual(type: number): boolean {
  return VIRTUAL_TYPES.has(type)
}

/**
 * Whether speed should be expressed in knots (marine sports), overriding the
 * user's metric/imperial preference, mirroring v1.
 *
 * @param type - Numeric activity type.
 * @returns Whether knots apply.
 */
export function activityTypeUsesKnots(type: number): boolean {
  return activityTypeIsSailing(type) || activityTypeIsWindsurf(type)
}

/**
 * Whether the activity is primarily distance-paced (pace metric) rather than
 * speed-based, mirroring v1's pace-vs-speed split.
 *
 * @param type - Numeric activity type.
 * @returns Whether pace (not speed) is the headline tempo metric.
 */
export function activityTypeUsesPace(type: number): boolean {
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
const NON_DISTANCE_TYPES = new Set([10, 14, 18, 19, 20, 41, 46, 47])

/**
 * Whether an activity is distance-based (shows distance/pace/elevation) versus
 * a non-distance session (gym/strength/racquet), mirroring v1's summary split.
 *
 * @param type - Numeric activity type.
 * @returns Whether the activity is distance-based.
 */
export function activityTypeIsDistanceBased(type: number): boolean {
  return !NON_DISTANCE_TYPES.has(type) && !activityTypeIsRacquet(type)
}

/**
 * Maps an activity type to one of the five badge colour categories the
 * {@link ActivityTypeBadge} primitive supports.
 *
 * @param type - Numeric activity type.
 * @returns The badge colour category.
 */
export function activityBadgeCategory(type: number): ActivityBadgeType {
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
 * @param type - Numeric activity type.
 * @returns The icon component.
 */
export function activityTypeIcon(type: number): LucideIcon {
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
 * @param type - Numeric activity type.
 * @returns The presentation bundle.
 */
export function presentActivityType(type: number): ActivityTypePresentation {
  return {
    labelKey: ACTIVITY_TYPE_LABEL_KEYS[type] ?? 'activities.types.workout',
    badge: activityBadgeCategory(type),
    icon: activityTypeIcon(type),
  }
}
