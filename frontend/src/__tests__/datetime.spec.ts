import { describe, expect, it, vi } from 'vitest'

import {
  formatMediumDate,
  formatMediumDateTime,
  formatRelativeTime,
  formatZonedDateTime,
  todayIsoDate,
} from '@/utils/datetime'

// Fixed reference point so assertions are deterministic regardless of the clock.
const now = new Date('2026-06-19T12:00:00Z')

describe('formatRelativeTime', () => {
  it('formats seconds in the past', () => {
    expect(formatRelativeTime('2026-06-19T11:59:30Z', now, 'en')).toBe('30 seconds ago')
  })

  it('formats minutes in the past', () => {
    expect(formatRelativeTime('2026-06-19T11:30:00Z', now, 'en')).toBe('30 minutes ago')
  })

  it('formats hours in the past', () => {
    expect(formatRelativeTime('2026-06-19T09:00:00Z', now, 'en')).toBe('3 hours ago')
  })

  it('uses natural wording for one day ago', () => {
    expect(formatRelativeTime('2026-06-18T12:00:00Z', now, 'en')).toBe('yesterday')
  })

  it('formats a future instant', () => {
    expect(formatRelativeTime('2026-06-19T14:00:00Z', now, 'en')).toBe('in 2 hours')
  })

  it('accepts a Date as well as an ISO string', () => {
    expect(formatRelativeTime(new Date('2026-06-19T11:30:00Z'), now, 'en')).toBe('30 minutes ago')
  })

  it('returns an empty string for an invalid date', () => {
    expect(formatRelativeTime('not-a-date', now, 'en')).toBe('')
  })
})

describe('todayIsoDate', () => {
  it('returns today as a yyyy-mm-dd string', () => {
    const result = todayIsoDate()
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it("uses the viewer's local calendar date, not the UTC one", () => {
    // 23:30 on 15 Jan in UTC+13 is still 10:30 UTC on the 15th... but at 13:30
    // UTC it is already the 16th locally. Anchoring on toISOString() reported
    // the UTC day, which is wrong for 13 of every 24 hours in that zone.
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date('2026-01-15T13:30:00Z'))
      const local = new Date()
      const expected = [
        local.getFullYear(),
        String(local.getMonth() + 1).padStart(2, '0'),
        String(local.getDate()).padStart(2, '0'),
      ].join('-')

      expect(todayIsoDate()).toBe(expected)
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('formatZonedDateTime', () => {
  // 2024-01-15T17:00:00Z is 09:00 in Los Angeles (UTC-8) and 18:00 in Lisbon.
  const instant = '2024-01-15T17:00:00Z'

  it("renders the instant in the activity's timezone, not the viewer's", () => {
    expect(
      formatZonedDateTime(instant, 'America/Los_Angeles', 'en', {
        dateStyle: 'medium',
        timeStyle: 'short',
      }),
    ).toBe('Jan 15, 2024, 9:00 AM')
  })

  it('is independent of the viewer timezone', () => {
    const asLisbon = formatZonedDateTime(instant, 'America/Los_Angeles', 'en', {
      timeStyle: 'short',
    })
    const asTokyo = formatZonedDateTime(instant, 'America/Los_Angeles', 'en', {
      timeStyle: 'short',
    })
    expect(asLisbon).toBe(asTokyo)
  })

  it('survives the viewer timezone DST gap', () => {
    // Europe/Lisbon skips 01:00->02:00 on 2024-03-31, so the wall clock "01:30"
    // does not exist there. The old approach fed that offset-less string to
    // new Date() in a Lisbon browser, which shifted it to 02:30. Formatting a
    // real instant in an explicit zone cannot drift: 08:30Z is 01:30 PDT.
    expect(
      formatZonedDateTime('2024-03-31T08:30:00Z', 'America/Los_Angeles', 'en', {
        timeStyle: 'short',
      }),
    ).toBe('1:30 AM')
  })

  it('falls back to the viewer timezone when the activity has none', () => {
    expect(formatZonedDateTime(instant, null, 'en', { dateStyle: 'short' })).not.toBe('')
  })

  it('falls back to the viewer timezone when the zone name is invalid', () => {
    expect(formatZonedDateTime(instant, 'Not/AZone', 'en', { dateStyle: 'short' })).not.toBe('')
  })

  it('returns an empty string for missing or unparseable input', () => {
    expect(formatZonedDateTime(null, 'UTC', 'en', { dateStyle: 'short' })).toBe('')
    expect(formatZonedDateTime('', 'UTC', 'en', { dateStyle: 'short' })).toBe('')
    expect(formatZonedDateTime('not-a-date', 'UTC', 'en', { dateStyle: 'short' })).toBe('')
  })
})

describe('formatMediumDate', () => {
  it('formats an ISO timestamp as a medium date', () => {
    // Noon UTC stays on the same calendar day across all real timezones.
    expect(formatMediumDate('2026-06-25T12:00:00Z', 'en')).toMatch(/^Jun \d{1,2}, 2026$/)
  })

  it('returns an empty string for an invalid date', () => {
    expect(formatMediumDate('not-a-date', 'en')).toBe('')
  })
})

describe('formatMediumDateTime', () => {
  it('appends a short time to the medium date', () => {
    const result = formatMediumDateTime('2026-06-25T12:00:00Z', 'en')
    expect(result).toMatch(/Jun \d{1,2}, 2026/)
    // A time component is appended, so the string is longer than the date alone.
    expect(result.length).toBeGreaterThan('Jun 25, 2026'.length)
  })

  it('returns an empty string for an invalid date', () => {
    expect(formatMediumDateTime('not-a-date', 'en')).toBe('')
  })
})
