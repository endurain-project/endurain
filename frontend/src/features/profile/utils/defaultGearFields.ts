import type { GearType } from '@/features/gears/types'
import type { DefaultGearValues } from '@/features/profile/types'

import { GEAR_TYPE } from '@/features/gears/utils/gearType'

/**
 * One activity's default-gear selector: which form field it binds and which
 * gear type populates its options.
 *
 * @property key - The {@link DefaultGearValues} field this selector edits.
 * @property labelKey - i18n key for the activity label.
 * @property gearType - The gear type whose gears are offered.
 */
export interface DefaultGearField {
  key: keyof DefaultGearValues
  labelKey: string
  gearType: GearType
}

/** A labelled group of default-gear selectors (mirrors v1's activity sections). */
export interface DefaultGearGroup {
  titleKey: string
  fields: DefaultGearField[]
}

/**
 * The default-gear selectors grouped by activity family, each field pointing at
 * the gear type that populates its options. This single source of truth drives
 * both the form layout and the set of gear types to prefetch.
 */
export const DEFAULT_GEAR_GROUPS: readonly DefaultGearGroup[] = [
  {
    titleKey: 'settings.profile.defaultGear.shoeActivities',
    fields: [
      { key: 'runGearId', labelKey: 'settings.profile.defaultGear.run', gearType: GEAR_TYPE.SHOES },
      {
        key: 'trailRunGearId',
        labelKey: 'settings.profile.defaultGear.trailRun',
        gearType: GEAR_TYPE.SHOES,
      },
      {
        key: 'virtualRunGearId',
        labelKey: 'settings.profile.defaultGear.virtualRun',
        gearType: GEAR_TYPE.SHOES,
      },
      {
        key: 'walkGearId',
        labelKey: 'settings.profile.defaultGear.walk',
        gearType: GEAR_TYPE.SHOES,
      },
      {
        key: 'hikeGearId',
        labelKey: 'settings.profile.defaultGear.hike',
        gearType: GEAR_TYPE.SHOES,
      },
    ],
  },
  {
    titleKey: 'settings.profile.defaultGear.bikeActivities',
    fields: [
      {
        key: 'rideGearId',
        labelKey: 'settings.profile.defaultGear.ride',
        gearType: GEAR_TYPE.BICYCLE,
      },
      {
        key: 'mtbRideGearId',
        labelKey: 'settings.profile.defaultGear.mtbRide',
        gearType: GEAR_TYPE.BICYCLE,
      },
      {
        key: 'gravelRideGearId',
        labelKey: 'settings.profile.defaultGear.gravelRide',
        gearType: GEAR_TYPE.BICYCLE,
      },
      {
        key: 'virtualRideGearId',
        labelKey: 'settings.profile.defaultGear.virtualRide',
        gearType: GEAR_TYPE.BICYCLE,
      },
    ],
  },
  {
    titleKey: 'settings.profile.defaultGear.waterActivities',
    fields: [
      {
        key: 'owsGearId',
        labelKey: 'settings.profile.defaultGear.ows',
        gearType: GEAR_TYPE.WETSUIT,
      },
      {
        key: 'windsurfGearId',
        labelKey: 'settings.profile.defaultGear.windsurf',
        gearType: GEAR_TYPE.WINDSURF,
      },
    ],
  },
  {
    titleKey: 'settings.profile.defaultGear.racquetActivities',
    fields: [
      {
        key: 'tennisGearId',
        labelKey: 'settings.profile.defaultGear.tennis',
        gearType: GEAR_TYPE.RACQUET,
      },
    ],
  },
  {
    titleKey: 'settings.profile.defaultGear.snowActivities',
    fields: [
      {
        key: 'alpineSkiGearId',
        labelKey: 'settings.profile.defaultGear.alpineSki',
        gearType: GEAR_TYPE.SKIS,
      },
      {
        key: 'nordicSkiGearId',
        labelKey: 'settings.profile.defaultGear.nordicSki',
        gearType: GEAR_TYPE.SKIS,
      },
      {
        key: 'snowboardGearId',
        labelKey: 'settings.profile.defaultGear.snowboard',
        gearType: GEAR_TYPE.SNOWBOARD,
      },
    ],
  },
]

/**
 * The distinct gear types referenced by the default-gear selectors, used to
 * prefetch exactly the gear lists the form needs (and no more).
 */
export const DEFAULT_GEAR_TYPES: readonly GearType[] = Array.from(
  new Set(DEFAULT_GEAR_GROUPS.flatMap((group) => group.fields.map((field) => field.gearType))),
)
