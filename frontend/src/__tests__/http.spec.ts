import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearAuthTokens, getAccessToken, setAuthTokens } from '@/services/authTokens'
import { apiFetch, HttpError } from '@/services/http'
import { onMfaEnrolmentRequired } from '@/services/mfaEnrolment'
import { onSessionExpired } from '@/services/sessionExpiry'

vi.mock('@/services/runtime', () => ({
  getApiBaseUrl: () => '',
  getRuntimeBackendHost: () => null,
  getBackendAssetUrl: (path: string) => path,
}))

vi.mock('@/services/authTokens', async (importActual) => ({
  ...(await importActual<typeof import('@/services/authTokens')>()),
  getAccessToken: vi.fn<typeof getAccessToken>(() => 'access-old'),
  setAuthTokens: vi.fn<typeof setAuthTokens>(),
  clearAuthTokens: vi.fn<typeof clearAuthTokens>(),
}))

/**
 * Builds a JSON Response, fresh per call so its body can be read once.
 *
 * @param body - Object to serialize, or `undefined` for an empty body.
 * @param status - HTTP status code.
 * @returns A Response instance.
 */
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const INVALID_TOKEN = 'urn:endurain:error:invalid-token'
const SESSION_ENDED = 'urn:endurain:error:session-ended'

const refreshTokenResponse = {
  next_step: 'tokens',
  access_token: 'access-new',
  session_id: '00000000-0000-4000-8000-0000000000f1',
  token_type: 'bearer',
  expires_in: 900,
  refresh_token_expires_in: 604_800,
}

const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  vi.mocked(setAuthTokens).mockClear()
  vi.mocked(clearAuthTokens).mockClear()
  vi.mocked(getAccessToken).mockReturnValue('access-old')
})

afterEach(() => {
  vi.unstubAllGlobals()
  onSessionExpired(null)
  onMfaEnrolmentRequired(null)
})

describe('apiFetch', () => {
  it('includes credentials and the bearer token, returning parsed JSON', async () => {
    let credentials: RequestCredentials | undefined
    let authHeader: string | null = null
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      credentials = init.credentials
      authHeader = (init.headers as Headers).get('Authorization')
      return Promise.resolve(jsonResponse({ value: 42 }))
    })

    const data = await apiFetch<{ value: number }>('/data')

    expect(data).toEqual({ value: 42 })
    expect(fetchMock).toHaveBeenCalledWith('/data', expect.anything())
    expect(credentials).toBe('include')
    expect(authHeader).toBe('Bearer access-old')
  })

  it('sends a JSON body with a JSON content type and no CSRF header', async () => {
    let csrf: string | null = 'unset'
    let contentType: string | null = null
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      const headers = init.headers as Headers
      csrf = headers.get('X-CSRF-Token')
      contentType = headers.get('Content-Type')
      return Promise.resolve(jsonResponse({}))
    })

    await apiFetch('/data', { method: 'POST', body: JSON.stringify({ a: 1 }) })

    expect(csrf).toBeNull()
    expect(contentType).toBe('application/json')
  })

  it('throws an HttpError carrying the backend detail', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Bad request' }, 400))

    const error = await apiFetch('/data').catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(HttpError)
    expect((error as HttpError).status).toBe(400)
    expect((error as HttpError).detail).toBe('Bad request')
  })

  it('refreshes once on 401 and retries the original request', async () => {
    let dataAttempts = 0
    let refreshCount = 0
    fetchMock.mockImplementation((url: string) => {
      if (url === '/auth/refresh') {
        refreshCount += 1
        return Promise.resolve(jsonResponse(refreshTokenResponse))
      }
      dataAttempts += 1
      return Promise.resolve(
        dataAttempts === 1
          ? jsonResponse({ type: INVALID_TOKEN }, 401)
          : jsonResponse({ ok: true }),
      )
    })

    const data = await apiFetch<{ ok: boolean }>('/data')

    expect(data).toEqual({ ok: true })
    expect(refreshCount).toBe(1)
    expect(setAuthTokens).toHaveBeenCalledWith('access-new')
  })

  it('coalesces concurrent 401 refreshes into a single refresh call', async () => {
    const attempts: Record<string, number> = {}
    let refreshCount = 0
    fetchMock.mockImplementation((url: string) => {
      if (url === '/auth/refresh') {
        refreshCount += 1
        return Promise.resolve(jsonResponse(refreshTokenResponse))
      }
      attempts[url] = (attempts[url] ?? 0) + 1
      return Promise.resolve(
        attempts[url] === 1 ? jsonResponse({ type: INVALID_TOKEN }, 401) : jsonResponse({ url }),
      )
    })

    await Promise.all([apiFetch('/a'), apiFetch('/b')])

    expect(refreshCount).toBe(1)
  })

  it('clears tokens and rejects when the refresh answers session-ended', async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        jsonResponse({ type: url === '/auth/refresh' ? SESSION_ENDED : INVALID_TOKEN }, 401),
      ),
    )

    await expect(apiFetch('/data')).rejects.toBeInstanceOf(HttpError)
    expect(clearAuthTokens).toHaveBeenCalled()
  })

  it.each([
    ['an MFA step', { next_step: 'mfa', mfa_challenge: 'c' }],
    ['no access token', { ...refreshTokenResponse, access_token: undefined }],
  ])(
    'refuses a refresh answer with %s, clears the tokens and signals expiry',
    async (_l, answer) => {
      const onExpired = vi.fn<() => void>()
      onSessionExpired(onExpired)
      fetchMock.mockImplementation((url: string) =>
        Promise.resolve(
          url === '/auth/refresh'
            ? jsonResponse(answer)
            : jsonResponse({ type: INVALID_TOKEN }, 401),
        ),
      )

      await expect(apiFetch('/data')).rejects.toBeInstanceOf(Error)
      expect(setAuthTokens).not.toHaveBeenCalled()
      expect(clearAuthTokens).toHaveBeenCalled()
      expect(onExpired).toHaveBeenCalledTimes(1)
    },
  )

  it('signals session expiry when a mid-session refresh answers session-ended', async () => {
    const onExpired = vi.fn<() => void>()
    onSessionExpired(onExpired)
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        jsonResponse({ type: url === '/auth/refresh' ? SESSION_ENDED : INVALID_TOKEN }, 401),
      ),
    )

    await expect(apiFetch('/data')).rejects.toBeInstanceOf(HttpError)
    expect(onExpired).toHaveBeenCalledTimes(1)
  })

  describe('when the refresh fails for a reason other than a rejected session', () => {
    /**
     * Makes the original request return an expired-token 401 and the refresh
     * answer as `refresh` dictates.
     *
     * @param refresh - Produces the outcome of the `/auth/refresh` call.
     */
    function expireSessionThenRefreshWith(refresh: () => Promise<Response>): void {
      fetchMock.mockImplementation((url: string) => {
        if (url === '/auth/refresh') return refresh()
        return Promise.resolve(jsonResponse({ type: INVALID_TOKEN, detail: 'expired' }, 401))
      })
    }

    it('keeps the tokens and does not signal expiry on a network error', async () => {
      const onExpired = vi.fn<() => void>()
      onSessionExpired(onExpired)
      const networkError = new TypeError('Failed to fetch')
      expireSessionThenRefreshWith(() => Promise.reject(networkError))

      await expect(apiFetch('/data')).rejects.toBe(networkError)
      expect(clearAuthTokens).not.toHaveBeenCalled()
      expect(onExpired).not.toHaveBeenCalled()
    })

    it('keeps the tokens and does not signal expiry on a 500', async () => {
      const onExpired = vi.fn<() => void>()
      onSessionExpired(onExpired)
      expireSessionThenRefreshWith(() => Promise.resolve(jsonResponse({ detail: 'boom' }, 500)))

      await expect(apiFetch('/data')).rejects.toMatchObject({ status: 500 })
      expect(clearAuthTokens).not.toHaveBeenCalled()
      expect(onExpired).not.toHaveBeenCalled()
    })

    it('keeps the tokens and does not signal expiry on a 429', async () => {
      const onExpired = vi.fn<() => void>()
      onSessionExpired(onExpired)
      expireSessionThenRefreshWith(() =>
        Promise.resolve(jsonResponse({ detail: 'slow down' }, 429)),
      )

      await expect(apiFetch('/data')).rejects.toMatchObject({ status: 429 })
      expect(clearAuthTokens).not.toHaveBeenCalled()
      expect(onExpired).not.toHaveBeenCalled()
    })

    it('keeps the tokens and does not signal expiry on a timeout', async () => {
      const onExpired = vi.fn<() => void>()
      onSessionExpired(onExpired)
      const timeout = new DOMException('The operation timed out.', 'TimeoutError')
      expireSessionThenRefreshWith(() => Promise.reject(timeout))

      await expect(apiFetch('/data')).rejects.toBe(timeout)
      expect(clearAuthTokens).not.toHaveBeenCalled()
      expect(onExpired).not.toHaveBeenCalled()
    })

    it('keeps the tokens and does not signal expiry on an abort', async () => {
      const onExpired = vi.fn<() => void>()
      onSessionExpired(onExpired)
      const abort = new DOMException('The operation was aborted.', 'AbortError')
      expireSessionThenRefreshWith(() => Promise.reject(abort))

      await expect(apiFetch('/data')).rejects.toBe(abort)
      expect(clearAuthTokens).not.toHaveBeenCalled()
      expect(onExpired).not.toHaveBeenCalled()
    })

    it('keeps the tokens and does not signal expiry on a 403 origin refusal', async () => {
      const onExpired = vi.fn<() => void>()
      onSessionExpired(onExpired)
      expireSessionThenRefreshWith(() =>
        Promise.resolve(
          jsonResponse({ type: 'urn:endurain:error:permission-denied', detail: 'Origin' }, 403),
        ),
      )

      await expect(apiFetch('/data')).rejects.toMatchObject({ status: 403 })
      expect(clearAuthTokens).not.toHaveBeenCalled()
      expect(onExpired).not.toHaveBeenCalled()
    })
  })

  it('returns a 401 with another problem type as-is, without refreshing or replaying', async () => {
    const onExpired = vi.fn<() => void>()
    onSessionExpired(onExpired)
    const calls: string[] = []
    fetchMock.mockImplementation((url: string) => {
      calls.push(url)
      return Promise.resolve(
        jsonResponse({ type: 'urn:endurain:error:unauthorized', detail: 'Invalid password' }, 401),
      )
    })

    await expect(apiFetch('/data', { method: 'POST' })).rejects.toMatchObject({
      status: 401,
      type: 'urn:endurain:error:unauthorized',
    })
    expect(calls).toEqual(['/data'])
    expect(onExpired).not.toHaveBeenCalled()
    expect(clearAuthTokens).not.toHaveBeenCalled()
  })

  it('does not attempt a refresh for the login endpoint', async () => {
    let refreshCount = 0
    fetchMock.mockImplementation((url: string) => {
      if (url === '/auth/refresh') refreshCount += 1
      return Promise.resolve(jsonResponse({ detail: 'bad credentials' }, 401))
    })

    await expect(
      apiFetch('/auth/login', { auth: false, retryOnUnauthorized: false }),
    ).rejects.toBeInstanceOf(HttpError)
    expect(refreshCount).toBe(0)
  })

  it('forwards the caller abort signal verbatim when the timeout is disabled', async () => {
    let forwardedSignal: AbortSignal | null | undefined
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      forwardedSignal = init.signal
      return Promise.resolve(jsonResponse({}))
    })
    const controller = new AbortController()

    await apiFetch('/data', { signal: controller.signal, timeoutMs: 0 })

    expect(forwardedSignal).toBe(controller.signal)
  })

  it('composes the caller signal with the timeout so caller aborts still propagate', async () => {
    let forwardedSignal: AbortSignal | undefined
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      forwardedSignal = init.signal ?? undefined
      return Promise.resolve(jsonResponse({}))
    })
    const controller = new AbortController()

    await apiFetch('/data', { signal: controller.signal })

    expect(forwardedSignal).toBeInstanceOf(AbortSignal)
    expect(forwardedSignal).not.toBe(controller.signal)
    controller.abort()
    expect(forwardedSignal?.aborted).toBe(true)
  })

  it('applies a default timeout signal when the caller provides none', async () => {
    let forwardedSignal: AbortSignal | undefined
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      forwardedSignal = init.signal ?? undefined
      return Promise.resolve(jsonResponse({}))
    })

    await apiFetch('/data')

    expect(forwardedSignal).toBeInstanceOf(AbortSignal)
  })
})

describe('Retry-After', () => {
  /**
   * Builds an empty error response carrying a `Retry-After` header.
   *
   * @param status - HTTP status code.
   * @param retryAfter - Header value, or `null` for none.
   * @returns A Response instance.
   */
  function throttled(status: number, retryAfter: string | null): Response {
    const headers = retryAfter === null ? undefined : { 'Retry-After': retryAfter }
    return new Response(null, { status, headers })
  }

  it.each([429, 503])('reads delta-seconds from a %i', async (status) => {
    fetchMock.mockResolvedValue(throttled(status, '30'))

    const error = await apiFetch('/data').catch((caught: unknown) => caught)

    expect((error as HttpError).retryAfterSeconds).toBe(30)
  })

  it('reads an HTTP-date as the seconds left until it', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-10T12:00:00Z'))
    fetchMock.mockResolvedValue(throttled(429, 'Tue, 10 Nov 2026 12:01:30 GMT'))

    const error = await apiFetch('/data').catch((caught: unknown) => caught)
    vi.useRealTimers()

    expect((error as HttpError).retryAfterSeconds).toBe(90)
  })

  it.each([null, 'soon', '-5', 'Tue, 10 Nov 2020 12:00:00 GMT'])(
    'has no wait time for %j',
    async (value) => {
      fetchMock.mockResolvedValue(throttled(429, value))

      const error = await apiFetch('/data').catch((caught: unknown) => caught)

      expect((error as HttpError).retryAfterSeconds).toBeNull()
    },
  )
})

describe('RFC 9457 problem documents', () => {
  it('carries the problem type and request id onto HttpError', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          type: 'urn:endurain:error:conflict',
          title: 'Conflict',
          status: 409,
          detail: 'Follow relationship already exists',
          instance: '/api/v1/followers/users/2/follow',
          request_id: 'req-abc',
        }),
        { status: 409, headers: { 'Content-Type': 'application/problem+json' } },
      ) as Response,
    )

    await expect(apiFetch('/followers/users/2/follow', { method: 'POST' })).rejects.toMatchObject({
      status: 409,
      type: 'urn:endurain:error:conflict',
      requestId: 'req-abc',
      detail: 'Follow relationship already exists',
    })
  })

  it('carries the running job a 409 names as jobId, and null when it names none', async () => {
    const conflict = (body: object) =>
      new Response(JSON.stringify({ type: 'urn:endurain:error:conflict', ...body }), {
        status: 409,
        headers: { 'Content-Type': 'application/problem+json' },
      }) as Response
    vi.mocked(fetch).mockResolvedValueOnce(
      conflict({ job_id: '00000000-0000-4000-8000-0000000000a9' }),
    )
    await expect(apiFetch('/profile/export', { method: 'POST' })).rejects.toMatchObject({
      jobId: '00000000-0000-4000-8000-0000000000a9',
    })

    vi.mocked(fetch).mockResolvedValueOnce(conflict({}))
    await expect(apiFetch('/profile/export', { method: 'POST' })).rejects.toMatchObject({
      jobId: null,
    })
  })

  it('tolerates a non-conforming error body', async () => {
    // A gateway or proxy error page must not become an unhandled parse failure.
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response('<html>502</html>', { status: 502 }) as Response,
    )

    await expect(apiFetch('/anything')).rejects.toMatchObject({
      status: 502,
      type: null,
      requestId: null,
    })
  })
})

describe('apiFetch when the server requires MFA enrolment', () => {
  const ENROLMENT_REQUIRED = 'urn:endurain:error:mfa-enrolment-required'

  it('signals once and still rejects with the problem type', async () => {
    const onRequired = vi.fn<() => void>()
    onMfaEnrolmentRequired(onRequired)
    fetchMock.mockResolvedValue(jsonResponse({ type: ENROLMENT_REQUIRED, detail: 'Set up' }, 403))

    await expect(apiFetch('/data')).rejects.toMatchObject({ status: 403, type: ENROLMENT_REQUIRED })
    expect(onRequired).toHaveBeenCalledTimes(1)
    // It is not a token problem: nothing is refreshed.
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not signal for any other 403', async () => {
    const onRequired = vi.fn<() => void>()
    onMfaEnrolmentRequired(onRequired)
    fetchMock.mockResolvedValue(
      jsonResponse({ type: 'urn:endurain:error:permission-denied', detail: 'no' }, 403),
    )

    await expect(apiFetch('/data')).rejects.toMatchObject({ status: 403 })
    expect(onRequired).not.toHaveBeenCalled()
  })

  it('does nothing when no handler is registered', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ type: ENROLMENT_REQUIRED, detail: 'Set up' }, 403))

    await expect(apiFetch('/data')).rejects.toBeInstanceOf(HttpError)
  })
})
