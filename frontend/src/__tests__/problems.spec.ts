import { describe, expect, it } from 'vitest'

import { HttpError } from '@/services/http'
import { isProblem, retryWaitMessage } from '@/services/problems'

const t = (key: string, params: { seconds: number }) => `${key}:${params.seconds}`

function problem(status: number, code: string | null, retryAfter: number | null = null) {
  return new HttpError(
    status,
    'x',
    null,
    code === null ? null : `urn:endurain:error:${code}`,
    null,
    [],
    retryAfter,
  )
}

describe('isProblem', () => {
  it('matches the type, not the status', () => {
    expect(isProblem(problem(409, 'conflict'), 'conflict')).toBe(true)
    expect(isProblem(problem(409, 'last-administrator'), 'conflict')).toBe(false)
    expect(isProblem(problem(409, null), 'conflict')).toBe(false)
  })

  it('accepts any of several codes', () => {
    expect(isProblem(problem(429, 'rate-limited'), 'too-many-requests', 'rate-limited')).toBe(true)
  })

  it('is false for a non-HttpError', () => {
    expect(isProblem(new Error('x'), 'conflict')).toBe(false)
    expect(isProblem(undefined, 'conflict')).toBe(false)
  })
})

describe('retryWaitMessage', () => {
  it('words a throttled response that names a wait', () => {
    expect(retryWaitMessage(problem(429, 'rate-limited', 30), t)).toBe(
      'app.retryAfter.tooManyAttempts:30',
    )
    expect(retryWaitMessage(problem(429, 'too-many-requests', 5), t)).toBe(
      'app.retryAfter.tooManyAttempts:5',
    )
  })

  it('words an unavailable response that names a wait', () => {
    expect(retryWaitMessage(problem(503, 'service-unavailable', 9), t)).toBe(
      'app.retryAfter.unavailable:9',
    )
  })

  it('returns null without a wait or for another problem', () => {
    expect(retryWaitMessage(problem(429, 'rate-limited'), t)).toBeNull()
    expect(retryWaitMessage(problem(400, 'invalid-input', 5), t)).toBeNull()
    expect(retryWaitMessage(new Error('x'), t)).toBeNull()
  })
})
