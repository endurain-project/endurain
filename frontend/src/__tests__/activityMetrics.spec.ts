import { describe, expect, it } from 'vitest'

import {
  activityDuration,
  buildActivityMetrics,
  distinctElapsedTime,
} from '@/features/activities/utils/metrics'

import { makeActivity } from './fixtures/activity'

const visible = {
  pace: true,
  speed: true,
  hr: true,
  power: true,
  cadence: true,
  elevation: true,
}

describe('activityDuration', () => {
  it('uses the timer time when it is positive', () => {
    expect(activityDuration(makeActivity({ totalTimerTime: 3500, totalElapsedTime: 3600 }))).toBe(
      3500,
    )
  })

  it('falls back to elapsed time when the timer time is 0', () => {
    expect(activityDuration(makeActivity({ totalTimerTime: 0, totalElapsedTime: 3600 }))).toBe(3600)
  })

  it('falls back to elapsed time when the timer time is null', () => {
    expect(activityDuration(makeActivity({ totalTimerTime: null, totalElapsedTime: 3600 }))).toBe(
      3600,
    )
  })

  it('returns null when both times are null', () => {
    expect(
      activityDuration(makeActivity({ totalTimerTime: null, totalElapsedTime: null })),
    ).toBeNull()
  })
})

describe('distinctElapsedTime', () => {
  it('returns elapsed time when it differs from the timer time', () => {
    expect(
      distinctElapsedTime(makeActivity({ totalTimerTime: 3500, totalElapsedTime: 3600 })),
    ).toBe(3600)
  })

  it('returns null when elapsed time is the duration already shown', () => {
    expect(
      distinctElapsedTime(makeActivity({ totalTimerTime: 3600, totalElapsedTime: 3600 })),
    ).toBeNull()
    expect(
      distinctElapsedTime(makeActivity({ totalTimerTime: 0, totalElapsedTime: 3600 })),
    ).toBeNull()
    expect(
      distinctElapsedTime(makeActivity({ totalTimerTime: 3500, totalElapsedTime: null })),
    ).toBeNull()
  })
})

describe('buildActivityMetrics time tile', () => {
  const timeTile = (totalTimerTime: number | null, totalElapsedTime: number | null) =>
    buildActivityMetrics(
      makeActivity({ activityType: 1, totalTimerTime, totalElapsedTime }),
      'metric',
      visible,
    ).find((tile) => tile.key === 'time')

  it('shows the timer time when it is positive', () => {
    expect(timeTile(3500, 3600)?.value).toBe('58:20')
  })

  it('shows elapsed time when the timer time is 0', () => {
    expect(timeTile(0, 3600)?.value).toBe('1:00:00')
  })

  it('shows elapsed time when the timer time is null', () => {
    expect(timeTile(null, 3600)?.value).toBe('1:00:00')
  })

  it('omits the tile when both times are null', () => {
    expect(timeTile(null, null)).toBeUndefined()
  })
})

describe('buildActivityMetrics elapsed tile', () => {
  const keysFor = (activityType: number, totalElapsedTime: number) =>
    buildActivityMetrics(
      makeActivity({ activityType, totalTimerTime: 600, totalElapsedTime }),
      'metric',
      visible,
    )

  it('adds elapsed time after the time tile for non-distance sessions when it differs', () => {
    const tiles = keysFor(19, 1200)
    expect(tiles.map((tile) => tile.key)).toEqual(['calories', 'time', 'elapsedTime', 'avgHr'])
    expect(tiles.find((tile) => tile.key === 'elapsedTime')?.value).toBe('20:00')
  })

  it('omits elapsed time for non-distance sessions when it matches the timer time', () => {
    expect(keysFor(19, 600).map((tile) => tile.key)).not.toContain('elapsedTime')
  })

  it('keeps elapsed time off the summary for distance activities', () => {
    expect(keysFor(1, 1200).map((tile) => tile.key)).not.toContain('elapsedTime')
  })
})
