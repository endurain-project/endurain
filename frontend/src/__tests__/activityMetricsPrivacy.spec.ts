import { describe, expect, it } from 'vitest'

import { buildActivityMetrics, formatLapTempo } from '@/features/activities/utils/metrics'
import {
  buildMetricVisibility,
  canViewField,
  hasHiddenFields,
  isActivityOwner,
  streamMetricVisibility,
} from '@/features/activities/utils/privacy'

import { makeActivity, NO_PRIVACY } from './fixtures/activity'

describe('isActivityOwner', () => {
  it('matches the owner only when ids align and a viewer is present', () => {
    const activity = makeActivity({ userId: 7 })
    expect(isActivityOwner(activity, 7)).toBe(true)
    expect(isActivityOwner(activity, 8)).toBe(false)
    expect(isActivityOwner(activity, null)).toBe(false)
  })
})

describe('canViewField', () => {
  it('lets the owner see hidden fields but hides them from others', () => {
    const activity = makeActivity({ userId: 7, privacy: { ...NO_PRIVACY, hideHr: true } })
    expect(canViewField(activity, 'hideHr', 7)).toBe(true)
    expect(canViewField(activity, 'hideHr', 8)).toBe(false)
    expect(canViewField(activity, 'hideHr', null)).toBe(false)
  })

  it('shows non-hidden fields to everyone', () => {
    const activity = makeActivity({ userId: 7 })
    expect(canViewField(activity, 'hidePower', 8)).toBe(true)
  })
})

describe('buildMetricVisibility', () => {
  it('shows everything to the owner', () => {
    const activity = makeActivity({ userId: 7, privacy: { ...NO_PRIVACY, hideHr: true } })
    expect(buildMetricVisibility(activity, 7).hr).toBe(true)
  })

  it('respects hide flags for non-owners', () => {
    const activity = makeActivity({ userId: 7, privacy: { ...NO_PRIVACY, hideHr: true } })
    const visibility = buildMetricVisibility(activity, 8)
    expect(visibility.hr).toBe(false)
    expect(visibility.pace).toBe(true)
  })
})

describe('streamMetricVisibility', () => {
  it('always shows temperature and gates hr by its flag', () => {
    const activity = makeActivity({ userId: 7, privacy: { ...NO_PRIVACY, hideHr: true } })
    const visible = streamMetricVisibility(activity, 8)
    expect(visible('temperature')).toBe(true)
    expect(visible('hr')).toBe(false)
    expect(visible('pace')).toBe(true)
  })
})

describe('hasHiddenFields', () => {
  it('detects any enabled hide flag', () => {
    expect(hasHiddenFields(makeActivity())).toBe(false)
    expect(hasHiddenFields(makeActivity({ privacy: { ...NO_PRIVACY, hideMap: true } }))).toBe(true)
  })
})

describe('buildActivityMetrics', () => {
  const visible = {
    pace: true,
    speed: true,
    hr: true,
    power: true,
    cadence: true,
    elevation: true,
  }

  it('uses moving (timer) time for the time tile, falling back to elapsed', () => {
    const timer = buildActivityMetrics(
      makeActivity({ activityType: 1, totalTimerTime: 3500, totalElapsedTime: 3600 }),
      'metric',
      visible,
    )
    expect(timer.find((tile) => tile.key === 'time')?.value).toBe('58:20')

    const elapsedOnly = buildActivityMetrics(
      makeActivity({ activityType: 1, totalTimerTime: null, totalElapsedTime: 3600 }),
      'metric',
      visible,
    )
    expect(elapsedOnly.find((tile) => tile.key === 'time')?.value).toBe('1:00:00')
  })

  it('shows a curated set of six running stats (distance/time/pace/power/elevation/calories)', () => {
    const tiles = buildActivityMetrics(
      makeActivity({ activityType: 1, averagePower: 250 }),
      'metric',
      visible,
    )
    const keys = tiles.map((tile) => tile.key)
    expect(keys).toEqual(['distance', 'time', 'pace', 'avgPower', 'elevationGain', 'calories'])
    expect(keys).not.toContain('avgSpeed')
    expect(tiles.length).toBeLessThanOrEqual(6)
  })

  it('shows speed (not pace) for cycling and caps at six', () => {
    const tiles = buildActivityMetrics(
      makeActivity({ activityType: 4, averageSpeed: 8, averagePower: 200, pace: null }),
      'metric',
      visible,
    )
    const keys = tiles.map((tile) => tile.key)
    expect(keys).toEqual(['distance', 'time', 'elevationGain', 'avgPower', 'avgSpeed', 'calories'])
    expect(keys).not.toContain('pace')
  })

  it('shows only calories/time/HR for non-distance activities (e.g. strength)', () => {
    const tiles = buildActivityMetrics(makeActivity({ activityType: 19 }), 'metric', visible)
    const keys = tiles.map((tile) => tile.key)
    expect(keys).toEqual(['calories', 'time', 'avgHr'])
    expect(keys).not.toContain('distance')
  })

  it('leads with a jumps tile for jump rope when total cycles are present', () => {
    const tiles = buildActivityMetrics(
      makeActivity({ activityType: 47, totalCycles: 1200 }),
      'metric',
      visible,
    )
    const jumps = tiles.find((tile) => tile.key === 'jumps')
    expect(tiles[0]?.key).toBe('jumps')
    expect(jumps?.value).toBe('1200')
    expect(jumps?.labelKey).toBe('activities.metrics.jumps')
  })

  it('omits the jumps tile for jump rope without total cycles', () => {
    const tiles = buildActivityMetrics(
      makeActivity({ activityType: 47, totalCycles: null }),
      'metric',
      visible,
    )
    expect(tiles.map((tile) => tile.key)).not.toContain('jumps')
  })

  it('does not show a jumps tile for other non-distance activities', () => {
    const tiles = buildActivityMetrics(
      makeActivity({ activityType: 19, totalCycles: 500 }),
      'metric',
      visible,
    )
    expect(tiles.map((tile) => tile.key)).not.toContain('jumps')
  })

  it('hides heart-rate tiles for a privacy-restricted swimmer but keeps pace', () => {
    const tiles = buildActivityMetrics(makeActivity({ activityType: 8 }), 'metric', {
      ...visible,
      hr: false,
    })
    const keys = tiles.map((tile) => tile.key)
    expect(keys).not.toContain('avgHr')
    expect(keys).not.toContain('maxHr')
    expect(keys).toContain('pace')
  })
})

describe('formatLapTempo', () => {
  it('uses pace for running and speed for cycling', () => {
    expect(formatLapTempo(0.3, null, 1, 'metric')).toBe('5:00 min/km')
    expect(formatLapTempo(null, 10, 4, 'metric')).toBe('36.00 km/h')
    expect(formatLapTempo(null, null, 1, 'metric')).toBe('--')
  })
})
