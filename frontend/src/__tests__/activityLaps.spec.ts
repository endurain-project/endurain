import { describe, expect, it } from 'vitest'

import type { ActivityLap } from '@/features/activities/types'
import { normalizeLaps, summarizeActiveLaps } from '@/features/activities/utils/laps'
import { activityUuid } from './fixtures/activity'

function makeLap(overrides: Partial<ActivityLap> = {}): ActivityLap {
  return {
    id: activityUuid(1),
    totalDistance: 1000,
    totalElapsedTime: 300,
    totalTimerTime: 300,
    enhancedAvgPace: 0.3,
    enhancedAvgSpeed: 3.3,
    totalAscent: 10,
    avgHeartRate: 150,
    avgCadence: 80,
    totalCycles: null,
    intensity: null,
    ...overrides,
  }
}

describe('normalizeLaps', () => {
  it('returns an empty array for no laps', () => {
    expect(normalizeLaps([], 'run')).toEqual([])
  })

  it('scores each lap relative to the fastest pace (non-swimming)', () => {
    const result = normalizeLaps(
      [
        makeLap({ id: activityUuid(1), enhancedAvgPace: 0.3 }),
        makeLap({ id: activityUuid(2), enhancedAvgPace: 0.4 }),
      ],
      'run',
    )
    expect(result.map((entry) => entry.swimIsRest)).toEqual([false, false])
    const scores = result.map((entry) => entry.normalizedScore)
    expect(scores[0]).toBe(100)
    expect(scores[1]).toBeCloseTo(75, 5)
  })

  it('returns a null score when a lap has no pace', () => {
    const result = normalizeLaps([makeLap({ id: activityUuid(1), enhancedAvgPace: null })], 'run')
    expect(result.map((entry) => entry.normalizedScore)).toEqual([null])
  })

  it('marks zero-distance swim laps as rests', () => {
    const result = normalizeLaps(
      [
        makeLap({ id: activityUuid(1), totalDistance: 50, enhancedAvgPace: 0.5 }),
        makeLap({ id: activityUuid(2), totalDistance: 0, enhancedAvgPace: null }),
        makeLap({ id: activityUuid(3), totalDistance: 50, enhancedAvgPace: 0.6 }),
      ],
      'lap_swimming',
    )
    expect(result.map((entry) => entry.swimIsRest)).toEqual([false, true, false])
  })

  it('treats two consecutive swim rests as a drill (second is not a rest)', () => {
    const result = normalizeLaps(
      [
        makeLap({ id: activityUuid(1), totalDistance: 0, enhancedAvgPace: null }),
        makeLap({ id: activityUuid(2), totalDistance: 0, enhancedAvgPace: null }),
      ],
      'lap_swimming',
    )
    expect(result.map((entry) => entry.swimIsRest)).toEqual([true, false])
  })

  it('never flags swim rests for non-swimming activities', () => {
    const result = normalizeLaps(
      [makeLap({ id: activityUuid(1), totalDistance: 0, enhancedAvgPace: null })],
      'run',
    )
    expect(result.map((entry) => entry.swimIsRest)).toEqual([false])
  })

  it('marks intensity="rest" laps as rests for any sport and nulls their score', () => {
    const result = normalizeLaps(
      [
        makeLap({ id: activityUuid(1), enhancedAvgPace: 0.3, intensity: 'active' }),
        makeLap({ id: activityUuid(2), enhancedAvgPace: 5, intensity: 'rest' }),
      ],
      'run',
    )
    expect(result.map((entry) => entry.isRest)).toEqual([false, true])
    expect(result.map((entry) => entry.swimIsRest)).toEqual([false, false])
    expect(result.map((entry) => entry.normalizedScore)).toEqual([100, null])
  })

  it('excludes rest laps from the fastest-pace baseline', () => {
    // The rest lap has an artificially fast pace; if it were part of the
    // baseline the active laps would score far below 100.
    const result = normalizeLaps(
      [
        makeLap({ id: activityUuid(1), enhancedAvgPace: 0.3, intensity: 'active' }),
        makeLap({ id: activityUuid(2), enhancedAvgPace: 0.1, intensity: 'rest' }),
        makeLap({ id: activityUuid(3), enhancedAvgPace: 0.4, intensity: 'active' }),
      ],
      'run',
    )
    const scores = result.map((entry) => entry.normalizedScore)
    expect(scores[0]).toBe(100)
    expect(scores[1]).toBeNull()
    expect(scores[2]).toBeCloseTo(75, 5)
  })
})

describe('summarizeActiveLaps', () => {
  it('returns null when there are no laps', () => {
    expect(summarizeActiveLaps([], 'run')).toBeNull()
  })

  it('sums only active laps and derives average speed and pace', () => {
    const summary = summarizeActiveLaps(
      [
        makeLap({
          id: activityUuid(1),
          totalDistance: 2000,
          totalElapsedTime: 400,
          intensity: 'active',
        }),
        makeLap({
          id: activityUuid(2),
          totalDistance: 20,
          totalElapsedTime: 120,
          intensity: 'rest',
        }),
        makeLap({
          id: activityUuid(3),
          totalDistance: 2000,
          totalElapsedTime: 400,
          intensity: 'active',
        }),
      ],
      'run',
    )
    expect(summary).not.toBeNull()
    expect(summary?.totalDistance).toBe(4000)
    expect(summary?.totalElapsedTime).toBe(800)
    expect(summary?.avgSpeed).toBeCloseTo(5, 5)
    expect(summary?.avgPace).toBeCloseTo(0.2, 5)
  })

  it('excludes swim rests (no intensity field) from the active totals', () => {
    // Swim rests are detected via the zero-distance heuristic, not an intensity
    // flag, so the summary must still separate them for swimming activities.
    const summary = summarizeActiveLaps(
      [
        makeLap({ id: activityUuid(1), totalDistance: 50, totalElapsedTime: 60, intensity: null }),
        makeLap({ id: activityUuid(2), totalDistance: 0, totalElapsedTime: 30, intensity: null }),
        makeLap({ id: activityUuid(3), totalDistance: 50, totalElapsedTime: 60, intensity: null }),
      ],
      'lap_swimming',
    )
    expect(summary).not.toBeNull()
    expect(summary?.totalDistance).toBe(100)
    expect(summary?.totalElapsedTime).toBe(120)
  })

  it('returns null when active laps have no usable distance or time', () => {
    const summary = summarizeActiveLaps(
      [
        makeLap({
          id: activityUuid(1),
          totalDistance: null,
          totalElapsedTime: null,
          intensity: 'active',
        }),
      ],
      'run',
    )
    expect(summary).toBeNull()
  })
})
