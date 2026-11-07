import { describe, expect, it } from 'vitest'

import { numberBetween } from '@/utils/validators'

describe('numberBetween', () => {
  const validate = numberBetween(1, 300, 'out of range')

  it('passes an empty value and values within the inclusive range', () => {
    expect(validate(null)).toBeNull()
    expect(validate('')).toBeNull()
    expect(validate('  ')).toBeNull()
    expect(validate(1)).toBeNull()
    expect(validate(300)).toBeNull()
    expect(validate('300')).toBeNull()
  })

  it('rejects values below the minimum and above the maximum', () => {
    expect(validate(0)).toBe('out of range')
    expect(validate(301)).toBe('out of range')
    expect(validate('0.5')).toBe('out of range')
  })

  it('applies only the minimum when no maximum is given', () => {
    const atLeastZero = numberBetween(0, undefined, 'too low')

    expect(atLeastZero('99999')).toBeNull()
    expect(atLeastZero('-1')).toBe('too low')
  })
})
