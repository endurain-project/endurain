import { describe, expect, it, vi } from 'vitest'

import type { UnitKey } from '@/i18n'

import {
  dateTimeLocalToIso,
  formatHealthChartLabel,
  formatHoursMinutes,
  formatRestingHeartRate,
  formatSkinTempDeviation,
  formatWater,
  formatWeight,
  localDayOf,
  nowDateTimeLocalInput,
  toDateTimeLocalInput,
} from '@/features/health/utils/healthFormat'

/** Wraps the unit key so a test can tell the resolver supplied the symbol. */
const label = (unit: UnitKey): string => `<${unit}>`

describe('unit-bearing formatters', () => {
  it('formatHoursMinutes hands the parts to the duration formatter and keeps zero hours', () => {
    const duration = vi.fn<(hours: number, minutes: number, showZeroHours?: boolean) => string>(
      () => 'formatted',
    )

    expect(formatHoursMinutes(29100, duration)).toBe('formatted')
    expect(duration).toHaveBeenCalledWith(8, 5, true)
    formatHoursMinutes(-30, duration)
    expect(duration).toHaveBeenLastCalledWith(0, 0, true)
  })

  it('formatRestingHeartRate rounds and takes the bpm symbol from the resolver', () => {
    expect(formatRestingHeartRate(51.6, label)).toBe('52 <bpm>')
  })

  it('formatSkinTempDeviation takes the Celsius symbol from the resolver', () => {
    expect(formatSkinTempDeviation(-1.24, label)).toBe('-1.2 <celsius>')
  })

  it('formatWeight picks kg or lb by unit system', () => {
    expect(formatWeight(72, 'metric', label)).toBe('72.0 <kg>')
    expect(formatWeight(72, 'imperial', label)).toBe('158.7 <lb>')
  })

  it('formatWater picks ml or fl oz by unit system', () => {
    expect(formatWater(1500.4, 'metric', label)).toBe('1500 <ml>')
    expect(formatWater(1500, 'imperial', label)).toBe('50.7 <flOz>')
  })
})

describe('datetime-local round trip', () => {
  it('converts a local wall clock to a real UTC instant', () => {
    const iso = dateTimeLocalToIso('2024-01-15T09:00')
    // Whatever the runner's zone, the instant must correspond to 09:00 local.
    expect(iso).not.toBeNull()
    expect(new Date(iso as string).getHours()).toBe(9)
  })

  it('round-trips through the stored instant unchanged', () => {
    const original = '2024-01-15T09:00'
    const iso = dateTimeLocalToIso(original) as string
    expect(toDateTimeLocalInput(iso)).toBe(original)
  })

  it('returns null / empty for missing or unparseable values', () => {
    expect(dateTimeLocalToIso('')).toBeNull()
    expect(dateTimeLocalToIso('nonsense')).toBeNull()
    expect(toDateTimeLocalInput(null)).toBe('')
    expect(toDateTimeLocalInput('nonsense')).toBe('')
  })

  it('nowDateTimeLocalInput yields the viewer local wall clock', () => {
    const now = new Date()
    const value = nowDateTimeLocalInput()
    expect(value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(Number(value.slice(11, 13))).toBe(now.getHours())
  })
})

describe('localDayOf', () => {
  it('buckets by the viewer local day, not the UTC slice', () => {
    // 2024-01-15T23:30Z is already the 16th for a viewer at UTC+9 and still the
    // 15th at UTC-5 — either way it must match the viewer's own calendar.
    const iso = '2024-01-15T23:30:00Z'
    const local = new Date(iso)
    const expected = [
      local.getFullYear(),
      String(local.getMonth() + 1).padStart(2, '0'),
      String(local.getDate()).padStart(2, '0'),
    ].join('-')

    expect(localDayOf(iso)).toBe(expected)
  })

  it('returns null for missing or unparseable values', () => {
    expect(localDayOf(null)).toBeNull()
    expect(localDayOf('nonsense')).toBeNull()
  })
})

describe('formatHealthChartLabel', () => {
  it('labels a monthly bucket with its month and year', () => {
    expect(formatHealthChartLabel('2026-06-01', 'month', 'en')).toBe('Jun 2026')
  })

  it.each(['day', 'week'] as const)('labels a %s bucket with its first day', (bucket) => {
    expect(formatHealthChartLabel('2026-06-22', bucket, 'en')).toBe('Jun 22, 2026')
  })

  it('returns an empty string for an unparseable date', () => {
    expect(formatHealthChartLabel('nonsense', 'month', 'en')).toBe('')
  })
})
