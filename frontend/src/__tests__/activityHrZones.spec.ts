import { afterEach, describe, expect, it } from 'vitest'

import type { ActivityStream, ActivityStreamType, HrZoneBucket } from '@/features/activities/types'

import { extractHrZones, hrZoneColor } from '@/features/activities/utils/hrZones'

/** Builds a stream fixture carrying optional HR zones. */
function stream(
  streamType: ActivityStreamType,
  hrZones: HrZoneBucket[] | null = null,
): ActivityStream {
  return { id: 1, streamType, waypoints: [], hrZones }
}

const ZONES: HrZoneBucket[] = [
  { zone: 1, percent: 25, hrRange: '< 100', timeSeconds: 900 },
  { zone: 2, percent: 30, hrRange: '100 - 129', timeSeconds: 1200 },
]

describe('extractHrZones', () => {
  it('returns the HR stream zones', () => {
    expect(extractHrZones([stream('elevation'), stream('heart_rate', ZONES)])).toEqual(ZONES)
  })

  it('returns null when the HR stream lacks zones or is absent', () => {
    expect(extractHrZones([stream('heart_rate', null)])).toBeNull()
    expect(extractHrZones([stream('elevation')])).toBeNull()
  })
})

describe('hrZoneColor', () => {
  afterEach(() => {
    document.documentElement.style.cssText = ''
  })

  it('reads zones 1, 2, 3 and 5 from the design tokens', () => {
    const root = document.documentElement
    root.style.setProperty('--color-info', '#111111')
    root.style.setProperty('--color-goal', '#222222')
    root.style.setProperty('--color-effort', '#333333')
    root.style.setProperty('--color-hr', '#555555')
    expect([1, 2, 3, 5].map(hrZoneColor)).toEqual(['#111111', '#222222', '#333333', '#555555'])
  })

  it('reads zone 4 from its design token, falling back to orange', () => {
    expect(hrZoneColor(4)).toBe('#f97316')
    document.documentElement.style.setProperty('--color-hr-zone-4', '#444444')
    expect(hrZoneColor(4)).toBe('#444444')
  })

  it('falls back to the top-zone colour out of range', () => {
    document.documentElement.style.setProperty('--color-hr', '#555555')
    expect(hrZoneColor(9)).toBe('#555555')
  })
})
