import { describe, expect, it } from 'vitest'

import {
  dateTimeLocalToIso,
  localDayOf,
  nowDateTimeLocalInput,
  toDateTimeLocalInput,
} from '@/features/health/utils/healthFormat'

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
