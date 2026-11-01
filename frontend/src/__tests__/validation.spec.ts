import { describe, expect, it } from 'vitest'

import { isValidEmail, isValidPassword, resolvePasswordMinLength } from '@/utils/validation'

describe('isValidEmail', () => {
  it('accepts a well-formed address and ignores surrounding whitespace', () => {
    expect(isValidEmail('user@example.com')).toBe(true)
    expect(isValidEmail('  user@example.com  ')).toBe(true)
  })

  it('rejects malformed addresses', () => {
    expect(isValidEmail('')).toBe(false)
    expect(isValidEmail('user@')).toBe(false)
    expect(isValidEmail('user@example')).toBe(false)
    expect(isValidEmail('user example.com')).toBe(false)
  })
})

describe('isValidPassword', () => {
  it('accepts any password of at least the minimum length', () => {
    expect(isValidPassword('aaaaaaaa', 8)).toBe(true)
    expect(isValidPassword('correct horse battery', 15)).toBe(true)
  })

  it('rejects passwords shorter than the minimum length', () => {
    expect(isValidPassword('aaaaaaa', 8)).toBe(false)
    expect(isValidPassword('Ab1!', 8)).toBe(false)
  })

  it('does not require any character class', () => {
    expect(isValidPassword('abcdefghijklmno', 15)).toBe(true)
  })

  it('counts Unicode characters of the NFC form, like the server', () => {
    // Seven emoji are 14 UTF-16 code units but 7 characters.
    expect(isValidPassword('😀'.repeat(7), 8)).toBe(false)
    // A decomposed "é" (e + combining accent) is one character once normalized.
    expect(isValidPassword('é'.repeat(7), 8)).toBe(false)
    expect(isValidPassword('é'.repeat(8), 8)).toBe(true)
  })
})

describe('resolvePasswordMinLength', () => {
  it('picks the admin length for admin accounts', () => {
    expect(resolvePasswordMinLength(8, 12, 'admin')).toBe(12)
  })

  it('picks the regular length for any other access type', () => {
    expect(resolvePasswordMinLength(8, 12, 'regular')).toBe(8)
    expect(resolvePasswordMinLength(8, 12, '')).toBe(8)
  })
})
