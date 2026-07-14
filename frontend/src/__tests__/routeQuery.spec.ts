import { describe, expect, it } from 'vitest'

import {
  getQueryString,
  getScalarQueryString,
  parseActivityTypeFilterQuery,
  parseIsoDateQuery,
} from '@/composables/useRouteQuery'

describe('getQueryString', () => {
  it('returns the first string from a query value array', () => {
    expect(getQueryString(['first', 'second'])).toBe('first')
  })

  it('returns an empty string for non-string values', () => {
    expect(getQueryString(undefined)).toBe('')
    expect(getQueryString(123)).toBe('')
  })
})

describe('getScalarQueryString', () => {
  it('rejects array query values', () => {
    expect(getScalarQueryString(['first', 'second'])).toBe('')
  })

  it('returns a single string query value', () => {
    expect(getScalarQueryString('value')).toBe('value')
  })
})

describe('parseActivityTypeFilterQuery', () => {
  it('accepts non-negative integer type codes', () => {
    expect(parseActivityTypeFilterQuery('0')).toBe(0)
    expect(parseActivityTypeFilterQuery('42')).toBe(42)
  })

  it('falls back to all types for invalid values', () => {
    expect(parseActivityTypeFilterQuery('-1')).toBe(0)
    expect(parseActivityTypeFilterQuery('1.5')).toBe(0)
    expect(parseActivityTypeFilterQuery('invalid')).toBe(0)
    expect(parseActivityTypeFilterQuery(['42', '0'])).toBe(0)
  })
})

describe('parseIsoDateQuery', () => {
  it('accepts ISO calendar dates', () => {
    expect(parseIsoDateQuery('2026-07-12')).toBe('2026-07-12')
  })

  it('uses the supplied fallback for malformed values', () => {
    expect(parseIsoDateQuery('12-07-2026', '2026-01-01')).toBe('2026-01-01')
    expect(parseIsoDateQuery(['2026-07-12'], '2026-01-01')).toBe('2026-01-01')
  })
})
