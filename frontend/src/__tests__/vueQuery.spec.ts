import { describe, expect, it } from 'vitest'

import { shouldRetryQuery } from '@/plugins/vueQuery'
import { HttpError } from '@/services/http'

describe('shouldRetryQuery', () => {
  const httpError = (status: number) => new HttpError(status, 'status')

  it('retries a network failure once', () => {
    expect(shouldRetryQuery(0, new TypeError('Failed to fetch'))).toBe(true)
    expect(shouldRetryQuery(1, new TypeError('Failed to fetch'))).toBe(false)
  })

  it('retries a timeout but not a deliberate abort', () => {
    expect(shouldRetryQuery(0, new DOMException('timed out', 'TimeoutError'))).toBe(true)
    expect(shouldRetryQuery(0, new DOMException('aborted', 'AbortError'))).toBe(false)
  })

  it('retries a 5xx once, except 501', () => {
    expect(shouldRetryQuery(0, httpError(500))).toBe(true)
    expect(shouldRetryQuery(0, httpError(503))).toBe(true)
    expect(shouldRetryQuery(1, httpError(503))).toBe(false)
    expect(shouldRetryQuery(0, httpError(501))).toBe(false)
  })

  it('never retries a 4xx, including 429', () => {
    for (const status of [400, 401, 404, 412, 429]) {
      expect(shouldRetryQuery(0, httpError(status))).toBe(false)
    }
  })
})
