import { afterEach, describe, expect, it, vi } from 'vitest'

import { setTelemetryAdapter } from '@/composables/useTelemetry'
import { queryClient, shouldReportError, shouldRetryQuery } from '@/plugins/vueQuery'
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

describe('shouldReportError', () => {
  it.each([400, 401, 403, 404, 412, 429])('does not report a %i', (status) => {
    expect(shouldReportError(new HttpError(status, 'status'))).toBe(false)
  })

  it.each([500, 503])('reports a %i', (status) => {
    expect(shouldReportError(new HttpError(status, 'status'))).toBe(true)
  })

  it('reports a network failure', () => {
    expect(shouldReportError(new TypeError('Failed to fetch'))).toBe(true)
  })

  it('does not report a deliberate abort', () => {
    expect(shouldReportError(new DOMException('aborted', 'AbortError'))).toBe(false)
  })
})

describe('queryClient error reporting', () => {
  const captureError = vi.fn<(error: unknown, context?: Record<string, unknown>) => void>()

  afterEach(() => {
    queryClient.clear()
    captureError.mockClear()
  })

  async function runQuery(key: string, error: unknown) {
    setTelemetryAdapter({ captureError, trackEvent: vi.fn<() => void>() })
    await queryClient
      .fetchQuery({
        queryKey: [key],
        queryFn: () => Promise.reject(error),
        retry: false,
      })
      .catch(() => undefined)
  }

  async function runMutation(error: unknown) {
    setTelemetryAdapter({ captureError, trackEvent: vi.fn<() => void>() })
    await queryClient
      .getMutationCache()
      .build(queryClient, { mutationFn: () => Promise.reject(error) })
      .execute(undefined)
      .catch(() => undefined)
  }

  it('reports a failed query for a 500 and a network error but not a 404', async () => {
    await runQuery('a', new HttpError(500, 'status'))
    await runQuery('b', new TypeError('Failed to fetch'))
    await runQuery('c', new HttpError(404, 'status'))

    expect(captureError).toHaveBeenCalledTimes(2)
  })

  it('reports a failed mutation for a 500 and a network error but not a 404', async () => {
    await runMutation(new HttpError(500, 'status'))
    await runMutation(new TypeError('Failed to fetch'))
    await runMutation(new HttpError(404, 'status'))

    expect(captureError).toHaveBeenCalledTimes(2)
  })
})
