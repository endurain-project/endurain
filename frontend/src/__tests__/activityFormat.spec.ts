import { describe, expect, it } from 'vitest'

import {
  cadenceUnitLabel,
  formatDistance,
  formatElevation,
  formatHmsDuration,
  formatPace,
  formatPaceClock,
  formatSpeed,
  paceToDisplaySeconds,
  speedToDisplay,
} from '@/features/activities/utils/format'

const RUN = 1
const CYCLE = 4
const SWIM = 8
const ROW = 13
const SAIL = 43

describe('formatHmsDuration', () => {
  it('formats durations over an hour as H:MM:SS', () => {
    expect(formatHmsDuration(3661)).toBe('1:01:01')
  })

  it('formats durations under an hour as MM:SS', () => {
    expect(formatHmsDuration(65)).toBe('01:05')
    expect(formatHmsDuration(0)).toBe('00:00')
  })

  it('returns a placeholder for missing or negative input', () => {
    expect(formatHmsDuration(null)).toBe('--')
    expect(formatHmsDuration(undefined)).toBe('--')
    expect(formatHmsDuration(-5)).toBe('--')
  })
})

describe('formatPaceClock', () => {
  it('rolls a rounded 60 seconds up to the next minute', () => {
    expect(formatPaceClock(300)).toBe('5:00')
    expect(formatPaceClock(359.6)).toBe('6:00')
    expect(formatPaceClock(305)).toBe('5:05')
  })
})

describe('formatPace', () => {
  it('formats running pace in min/km (metric) and min/mi (imperial)', () => {
    // 0.3 s/m = 300 s/km = 5:00/km.
    expect(formatPace(0.3, RUN, 'metric')).toEqual({ value: '5:00', unit: 'min/km' })
    // 0.3 s/m × 1609.34 = 482.8 s/mi ≈ 8:03/mi.
    expect(formatPace(0.3, RUN, 'imperial')).toEqual({ value: '8:03', unit: 'min/mi' })
  })

  it('formats swimming pace per 100m / 100yd', () => {
    // 0.9 s/m = 90 s/100m = 1:30/100m.
    expect(formatPace(0.9, SWIM, 'metric')).toEqual({ value: '1:30', unit: 'min/100m' })
    expect(formatPace(0.9, SWIM, 'imperial').unit).toBe('min/100yd')
  })

  it('formats rowing pace per 500m regardless of unit system', () => {
    // 0.24 s/m = 120 s/500m = 2:00/500m.
    expect(formatPace(0.24, ROW, 'metric')).toEqual({ value: '2:00', unit: 'min/500m' })
    expect(formatPace(0.24, ROW, 'imperial').unit).toBe('min/500m')
  })

  it('returns a placeholder for missing or non-positive pace', () => {
    expect(formatPace(null, RUN, 'metric').value).toBe('--')
    expect(formatPace(0, RUN, 'metric').value).toBe('--')
  })
})

describe('paceToDisplaySeconds', () => {
  it('converts to the activity-appropriate display unit seconds', () => {
    expect(paceToDisplaySeconds(0.3, RUN, 'metric')).toBeCloseTo(300)
    expect(paceToDisplaySeconds(0.9, SWIM, 'metric')).toBeCloseTo(90)
    expect(paceToDisplaySeconds(0.24, ROW, 'metric')).toBeCloseTo(120)
  })
})

describe('formatSpeed', () => {
  it('formats cycling speed in km/h and mph', () => {
    expect(formatSpeed(10, CYCLE, 'metric')).toEqual({ value: '36.00', unit: 'km/h' })
    expect(formatSpeed(10, CYCLE, 'imperial')).toEqual({ value: '22.37', unit: 'mph' })
  })

  it('uses knots for marine sports regardless of unit system', () => {
    expect(formatSpeed(10, SAIL, 'metric')).toEqual({ value: '19.44', unit: 'kn' })
    expect(formatSpeed(10, SAIL, 'imperial').unit).toBe('kn')
  })
})

describe('speedToDisplay', () => {
  it('returns the numeric converted speed', () => {
    expect(speedToDisplay(10, CYCLE, 'metric')).toBeCloseTo(36)
    expect(speedToDisplay(10, SAIL, 'metric')).toBeCloseTo(19.4384)
  })
})

describe('formatDistance', () => {
  it('formats non-swimming distance in km/mi', () => {
    expect(formatDistance(5000, RUN, 'metric')).toEqual({ value: '5.00', unit: 'km' })
    expect(formatDistance(5000, RUN, 'imperial')).toEqual({ value: '3.11', unit: 'mi' })
  })

  it('formats swimming distance in metres/yards', () => {
    expect(formatDistance(1000, SWIM, 'metric')).toEqual({ value: '1000', unit: 'm' })
    expect(formatDistance(1000, SWIM, 'imperial')).toEqual({ value: '1094', unit: 'yd' })
  })
})

describe('formatElevation', () => {
  it('formats elevation in metres or feet', () => {
    expect(formatElevation(100, 'metric')).toEqual({ value: '100', unit: 'm' })
    expect(formatElevation(100, 'imperial')).toEqual({ value: '328', unit: 'ft' })
  })

  it('returns a placeholder for missing input', () => {
    expect(formatElevation(null, 'metric').value).toBe('--')
  })
})

describe('cadenceUnitLabel', () => {
  it('labels cadence as spm for running and rpm otherwise', () => {
    expect(cadenceUnitLabel(RUN)).toBe('spm')
    expect(cadenceUnitLabel(CYCLE)).toBe('rpm')
  })
})
