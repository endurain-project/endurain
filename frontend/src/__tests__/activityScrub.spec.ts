import { describe, expect, it } from 'vitest'

import {
  indexAtFraction,
  nearestTrackIndex,
  pointAtFraction,
} from '@/features/activities/utils/scrub'

describe('indexAtFraction', () => {
  it('uses the ends and the middle of the series', () => {
    expect(indexAtFraction(5, 0)).toBe(0)
    expect(indexAtFraction(5, 1)).toBe(4)
    expect(indexAtFraction(5, 0.5)).toBe(2)
  })

  it('clamps a fraction outside 0 to 1', () => {
    expect(indexAtFraction(5, -2)).toBe(0)
    expect(indexAtFraction(5, 3)).toBe(4)
  })
})

describe('pointAtFraction', () => {
  const points = [
    { lat: 1, lng: 10 },
    { lat: 2, lng: 20 },
    { lat: 3, lng: 30 },
  ]

  it('returns the point at that fraction', () => {
    expect(pointAtFraction(points, 1)).toEqual({ lat: 3, lng: 30 })
  })

  it('returns null for an empty route', () => {
    expect(pointAtFraction([], 0.4)).toBeNull()
  })
})

describe('nearestTrackIndex', () => {
  const points = [
    { lat: 0, lng: 0 },
    { lat: 0, lng: 10 },
    { lat: 0, lng: 20 },
  ]

  it('returns the closest vertex', () => {
    expect(nearestTrackIndex(points, 0.1, 9)).toBe(1)
    expect(nearestTrackIndex(points, 0, 19)).toBe(2)
  })
})
