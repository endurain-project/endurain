import { describe, expect, it } from 'vitest'

import type { ActivityType } from '@/features/activities/types'

import {
  ACTIVITY_CATEGORY_FILTERS,
  ALL_ACTIVITY_CATEGORIES,
  ALL_GEAR_TYPES,
  filterActivitiesByCategory,
  filterGearsByType,
} from '@/features/search/utils/filters'

/** Minimal activity shape the filter reads (one representative type per family). */
const activities: { activityType: ActivityType }[] = [
  { activityType: 'run' }, // running
  { activityType: 'ride' }, // cycling
  { activityType: 'lap_swimming' }, // swimming
  { activityType: 'walk' }, // walking
  { activityType: 'tennis' }, // racquet
  { activityType: 'rowing' }, // rowing
  { activityType: 'alpine_ski' }, // snow skiing -> winterSports
  { activityType: 'snowboard' }, // snowboarding -> winterSports
  { activityType: 'ice_skate' }, // ice skating -> winterSports
  { activityType: 'windsurf' }, // windsurf -> waterSports
  { activityType: 'sailing' }, // sailing -> waterSports
  { activityType: 'stand_up_paddling' }, // stand-up paddling -> waterSports
  { activityType: 'surf' }, // surf -> waterSports
  { activityType: 'inline_skating' }, // inline skating -> skating
]

describe('filterActivitiesByCategory', () => {
  it('returns a copy of every activity for the "all" sentinel', () => {
    const result = filterActivitiesByCategory(activities, ALL_ACTIVITY_CATEGORIES)

    expect(result).toHaveLength(activities.length)
    expect(result).not.toBe(activities)
  })

  it('returns every activity for an unknown category', () => {
    expect(filterActivitiesByCategory(activities, 'does-not-exist')).toHaveLength(activities.length)
  })

  it('keeps only single-family disciplines', () => {
    expect(filterActivitiesByCategory(activities, 'running')).toEqual([{ activityType: 'run' }])
    expect(filterActivitiesByCategory(activities, 'cycling')).toEqual([{ activityType: 'ride' }])
    expect(filterActivitiesByCategory(activities, 'swimming')).toEqual([
      { activityType: 'lap_swimming' },
    ])
    expect(filterActivitiesByCategory(activities, 'racquet')).toEqual([{ activityType: 'tennis' }])
    expect(filterActivitiesByCategory(activities, 'rowing')).toEqual([{ activityType: 'rowing' }])
  })

  it('groups skiing, snowboarding, and ice skating under winter sports', () => {
    expect(filterActivitiesByCategory(activities, 'winterSports')).toEqual([
      { activityType: 'alpine_ski' },
      { activityType: 'snowboard' },
      { activityType: 'ice_skate' },
    ])
  })

  it('groups windsurf, sailing, paddling, and surf under water sports', () => {
    expect(filterActivitiesByCategory(activities, 'waterSports')).toEqual([
      { activityType: 'windsurf' },
      { activityType: 'sailing' },
      { activityType: 'stand_up_paddling' },
      { activityType: 'surf' },
    ])
  })

  it('keeps inline skating separate from ice skating', () => {
    expect(filterActivitiesByCategory(activities, 'skating')).toEqual([
      { activityType: 'inline_skating' },
    ])
  })

  it('exposes a stable, duplicate-free set of category values', () => {
    const values = ACTIVITY_CATEGORY_FILTERS.map((filter) => filter.value)

    expect(new Set(values).size).toBe(values.length)
    expect(values.every((value) => value.length > 0)).toBe(true)
  })
})

describe('filterGearsByType', () => {
  const gears = [
    { gearType: 'bike' as const },
    { gearType: 'shoes' as const },
    { gearType: 'shoes' as const },
    { gearType: 'ski' as const },
  ]

  it('returns a copy of every gear for the "all" sentinel', () => {
    const result = filterGearsByType(gears, ALL_GEAR_TYPES)

    expect(result).toHaveLength(gears.length)
    expect(result).not.toBe(gears)
  })

  it('keeps only gears of the requested type', () => {
    expect(filterGearsByType(gears, 'shoes')).toEqual([
      { gearType: 'shoes' },
      { gearType: 'shoes' },
    ])
    expect(filterGearsByType(gears, 'ski')).toEqual([{ gearType: 'ski' }])
  })

  it('returns nothing for a type with no matches', () => {
    expect(filterGearsByType(gears, 'wetsuit')).toEqual([])
  })
})
