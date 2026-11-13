import { describe, expect, it } from 'vitest'
import { Bike, Footprints, Sailboat, Waves } from '@lucide/vue'

import {
  activityBadgeCategory,
  activityTypeIsCycling,
  activityTypeIsRunning,
  activityTypeIsSwimming,
  activityTypeIsVirtual,
  activityTypeToGearType,
  activityTypeUsesKnots,
  activityTypeUsesPace,
  lapCyclesLabelKey,
  presentActivityType,
  sortActivityTypesByLabel,
} from '@/features/activities/utils/activityType'
import type { ActivityType } from '@/features/activities/types'
import { GEAR_TYPE } from '@/features/gears/utils/gearType'

/** A type a newer backend may send that this client does not know yet. */
const UNKNOWN = 'curling' as ActivityType

describe('activityTypeToGearType', () => {
  it('maps each activity family to its gear type (v1 parity)', () => {
    expect(activityTypeToGearType('ride')).toBe(GEAR_TYPE.BICYCLE)
    expect(activityTypeToGearType('run')).toBe(GEAR_TYPE.SHOES)
    expect(activityTypeToGearType('walk')).toBe(GEAR_TYPE.SHOES)
    expect(activityTypeToGearType('lap_swimming')).toBe(GEAR_TYPE.WETSUIT)
    expect(activityTypeToGearType('tennis')).toBe(GEAR_TYPE.RACQUET)
    expect(activityTypeToGearType('alpine_ski')).toBe(GEAR_TYPE.SKIS)
    expect(activityTypeToGearType('snowboard')).toBe(GEAR_TYPE.SNOWBOARD)
    expect(activityTypeToGearType('windsurf')).toBe(GEAR_TYPE.WINDSURF)
    expect(activityTypeToGearType('stand_up_paddling')).toBe(GEAR_TYPE.WATER_SPORTS_BOARD)
    expect(activityTypeToGearType('surf')).toBe(GEAR_TYPE.WATER_SPORTS_BOARD)
  })

  it('prefers shoes over snow gear for snowshoeing (snow_shoeing, in both groups)', () => {
    expect(activityTypeToGearType('snow_shoeing')).toBe(GEAR_TYPE.SHOES)
  })

  it('returns null for activity families with no associated gear', () => {
    expect(activityTypeToGearType('strength_training')).toBeNull()
    expect(activityTypeToGearType('hiit')).toBeNull()
  })
})

describe('activity type predicates', () => {
  it('classifies running, cycling and swimming types', () => {
    expect(activityTypeIsRunning('run')).toBe(true)
    expect(activityTypeIsRunning('ride')).toBe(false)
    expect(activityTypeIsCycling('ride')).toBe(true)
    expect(activityTypeIsSwimming('lap_swimming')).toBe(true)
    expect(activityTypeIsSwimming('open_water_swimming')).toBe(true)
  })

  it('flags virtual run/ride types', () => {
    expect(activityTypeIsVirtual('virtual_run')).toBe(true)
    expect(activityTypeIsVirtual('virtual_ride')).toBe(true)
    expect(activityTypeIsVirtual('run')).toBe(false)
  })

  it('uses pace for foot/water sports and speed for cycling', () => {
    expect(activityTypeUsesPace('run')).toBe(true)
    expect(activityTypeUsesPace('lap_swimming')).toBe(true)
    expect(activityTypeUsesPace('rowing')).toBe(true)
    expect(activityTypeUsesPace('ride')).toBe(false)
  })

  it('uses knots for marine sports', () => {
    expect(activityTypeUsesKnots('sailing')).toBe(true)
    expect(activityTypeUsesKnots('windsurf')).toBe(true)
    expect(activityTypeUsesKnots('ride')).toBe(false)
  })
})

describe('lapCyclesLabelKey', () => {
  it('labels the cycle column per sport', () => {
    expect(lapCyclesLabelKey('rowing')).toBe('activities.laps.strokes') // rowing
    expect(lapCyclesLabelKey('kayaking')).toBe('activities.laps.strokes') // kayaking
    expect(lapCyclesLabelKey('stand_up_paddling')).toBe('activities.laps.strokes') // SUP
    expect(lapCyclesLabelKey('lap_swimming')).toBe('activities.laps.strokes') // swimming
    expect(lapCyclesLabelKey('ride')).toBe('activities.laps.revolutions') // cycling
    expect(lapCyclesLabelKey('run')).toBe('activities.laps.strides') // running
    expect(lapCyclesLabelKey('walk')).toBe('activities.laps.strides') // walking
    expect(lapCyclesLabelKey('jump_rope')).toBe('activities.laps.jumps') // jump rope
  })

  it('falls back to the generic cycles label', () => {
    expect(lapCyclesLabelKey('workout')).toBe('activities.laps.cycles') // workout
    expect(lapCyclesLabelKey(UNKNOWN)).toBe('activities.laps.cycles')
  })
})

describe('activityBadgeCategory', () => {
  it('maps each discipline to a badge colour category', () => {
    expect(activityBadgeCategory('run')).toBe('running')
    expect(activityBadgeCategory('ride')).toBe('cycling')
    expect(activityBadgeCategory('lap_swimming')).toBe('swimming')
    expect(activityBadgeCategory('walk')).toBe('hiking')
    expect(activityBadgeCategory('tennis')).toBe('other')
  })
})

describe('presentActivityType', () => {
  it('bundles label key, badge and icon for known types', () => {
    expect(presentActivityType('run')).toEqual({
      labelKey: 'activities.types.run',
      badge: 'running',
      icon: Footprints,
    })
    expect(presentActivityType('ride').icon).toBe(Bike)
    expect(presentActivityType('lap_swimming').icon).toBe(Waves)
    expect(presentActivityType('sailing').icon).toBe(Sailboat)
  })

  it('falls back to a generic workout label for unknown types', () => {
    expect(presentActivityType(UNKNOWN).labelKey).toBe('activities.types.workout')
  })
})

describe('sortActivityTypesByLabel', () => {
  const labels: Record<string, string> = {
    [presentActivityType('run').labelKey]: 'Zebra',
    [presentActivityType('ride').labelKey]: 'Ärger',
    [presentActivityType('lap_swimming').labelKey]: 'Apfel',
  }
  const t = (key: string) => labels[key]!

  it('orders by translated label, not by key', () => {
    expect(sortActivityTypesByLabel(['run', 'ride', 'lap_swimming'], t, 'en')).toEqual([
      'lap_swimming',
      'ride',
      'run',
    ])
  })

  it('follows the locale collation rules', () => {
    // German sorts Ä with A; Swedish sorts Ä after Z.
    expect(sortActivityTypesByLabel(['run', 'ride', 'lap_swimming'], t, 'de')).toEqual([
      'lap_swimming',
      'ride',
      'run',
    ])
    expect(sortActivityTypesByLabel(['run', 'ride', 'lap_swimming'], t, 'sv')).toEqual([
      'lap_swimming',
      'run',
      'ride',
    ])
  })
})
