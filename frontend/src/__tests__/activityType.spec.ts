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
} from '@/features/activities/utils/activityType'
import { GEAR_TYPE } from '@/features/gears/utils/gearType'

describe('activityTypeToGearType', () => {
  it('maps each activity family to its gear type (v1 parity)', () => {
    expect(activityTypeToGearType(4)).toBe(GEAR_TYPE.BICYCLE)
    expect(activityTypeToGearType(1)).toBe(GEAR_TYPE.SHOES)
    expect(activityTypeToGearType(11)).toBe(GEAR_TYPE.SHOES)
    expect(activityTypeToGearType(8)).toBe(GEAR_TYPE.WETSUIT)
    expect(activityTypeToGearType(21)).toBe(GEAR_TYPE.RACQUET)
    expect(activityTypeToGearType(15)).toBe(GEAR_TYPE.SKIS)
    expect(activityTypeToGearType(17)).toBe(GEAR_TYPE.SNOWBOARD)
    expect(activityTypeToGearType(30)).toBe(GEAR_TYPE.WINDSURF)
    expect(activityTypeToGearType(32)).toBe(GEAR_TYPE.WATER_SPORTS_BOARD)
    expect(activityTypeToGearType(33)).toBe(GEAR_TYPE.WATER_SPORTS_BOARD)
  })

  it('prefers shoes over snow gear for snowshoeing (type 44, in both groups)', () => {
    expect(activityTypeToGearType(44)).toBe(GEAR_TYPE.SHOES)
  })

  it('returns null for activity families with no associated gear', () => {
    expect(activityTypeToGearType(19)).toBeNull()
    expect(activityTypeToGearType(46)).toBeNull()
  })
})

describe('activity type predicates', () => {
  it('classifies running, cycling and swimming types', () => {
    expect(activityTypeIsRunning(1)).toBe(true)
    expect(activityTypeIsRunning(4)).toBe(false)
    expect(activityTypeIsCycling(4)).toBe(true)
    expect(activityTypeIsSwimming(8)).toBe(true)
    expect(activityTypeIsSwimming(9)).toBe(true)
  })

  it('flags virtual run/ride types', () => {
    expect(activityTypeIsVirtual(3)).toBe(true)
    expect(activityTypeIsVirtual(7)).toBe(true)
    expect(activityTypeIsVirtual(1)).toBe(false)
  })

  it('uses pace for foot/water sports and speed for cycling', () => {
    expect(activityTypeUsesPace(1)).toBe(true)
    expect(activityTypeUsesPace(8)).toBe(true)
    expect(activityTypeUsesPace(13)).toBe(true)
    expect(activityTypeUsesPace(4)).toBe(false)
  })

  it('uses knots for marine sports', () => {
    expect(activityTypeUsesKnots(43)).toBe(true)
    expect(activityTypeUsesKnots(30)).toBe(true)
    expect(activityTypeUsesKnots(4)).toBe(false)
  })
})

describe('lapCyclesLabelKey', () => {
  it('labels the cycle column per sport', () => {
    expect(lapCyclesLabelKey(13)).toBe('activities.laps.strokes') // rowing
    expect(lapCyclesLabelKey(42)).toBe('activities.laps.strokes') // kayaking
    expect(lapCyclesLabelKey(32)).toBe('activities.laps.strokes') // SUP
    expect(lapCyclesLabelKey(8)).toBe('activities.laps.strokes') // swimming
    expect(lapCyclesLabelKey(4)).toBe('activities.laps.revolutions') // cycling
    expect(lapCyclesLabelKey(1)).toBe('activities.laps.strides') // running
    expect(lapCyclesLabelKey(11)).toBe('activities.laps.strides') // walking
    expect(lapCyclesLabelKey(47)).toBe('activities.laps.jumps') // jump rope
  })

  it('falls back to the generic cycles label', () => {
    expect(lapCyclesLabelKey(10)).toBe('activities.laps.cycles') // workout
    expect(lapCyclesLabelKey(999)).toBe('activities.laps.cycles')
  })
})

describe('activityBadgeCategory', () => {
  it('maps each discipline to a badge colour category', () => {
    expect(activityBadgeCategory(1)).toBe('running')
    expect(activityBadgeCategory(4)).toBe('cycling')
    expect(activityBadgeCategory(8)).toBe('swimming')
    expect(activityBadgeCategory(11)).toBe('hiking')
    expect(activityBadgeCategory(21)).toBe('other')
  })
})

describe('presentActivityType', () => {
  it('bundles label key, badge and icon for known types', () => {
    expect(presentActivityType(1)).toEqual({
      labelKey: 'activities.types.run',
      badge: 'running',
      icon: Footprints,
    })
    expect(presentActivityType(4).icon).toBe(Bike)
    expect(presentActivityType(8).icon).toBe(Waves)
    expect(presentActivityType(43).icon).toBe(Sailboat)
  })

  it('falls back to a generic workout label for unknown types', () => {
    expect(presentActivityType(999).labelKey).toBe('activities.types.workout')
  })
})
