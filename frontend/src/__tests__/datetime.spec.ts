import { describe, expect, it } from 'vitest'

import {
  formatMediumDate,
  formatMediumDateTime,
  formatRelativeTime,
  shiftWeeks,
  todayIsoDate,
  weekEnd,
  weekStart,
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
    expect(result).toBe(new Date().toISOString().slice(0, 10))
  })
})

describe('configurable week boundaries', () => {
  it('uses Sunday as the first day when configured', () => {
    expect(weekStart('2024-01-15', 'sunday')).toBe('2024-01-14')
    expect(weekEnd('2024-01-15', 'sunday')).toBe('2024-01-20')
  })

  it('supports arbitrary configured first days', () => {
    expect(weekStart('2024-01-15', 'wednesday')).toBe('2024-01-10')
    expect(weekEnd('2024-01-15', 'wednesday')).toBe('2024-01-16')
  })

  it('shifts dates by whole weeks', () => {
    expect(shiftWeeks('2024-01-14', -1)).toBe('2024-01-07')
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
