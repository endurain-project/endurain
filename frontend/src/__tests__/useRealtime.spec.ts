import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  JOB_POLL_CONNECTED_MS,
  jobPollInterval,
  useRealtime,
  watchJob,
} from '@/composables/useRealtime'

const invalidateQueries = vi.fn<(...args: unknown[]) => Promise<void>>((..._args) =>
  Promise.resolve(),
)

vi.mock('@/plugins/vueQuery', () => ({
  queryClient: { invalidateQueries: (...args: unknown[]) => invalidateQueries(...args) },
}))

vi.mock('@/services/runtime', () => ({
  getWebSocketUrl: () => 'ws://backend.test/ws',
}))

vi.mock('@/composables/useTelemetry', () => ({
  useTelemetry: () => ({ captureError: vi.fn<() => void>(), trackEvent: vi.fn<() => void>() }),
}))

const getAccessToken = vi.fn<() => string | null>(() => 'token-abc')
vi.mock('@/services/authTokens', () => ({
  getAccessToken: () => getAccessToken(),
}))

const apiFetch = vi.fn<(path: string, init?: { method?: string }) => Promise<{ ticket: string }>>(
  () => Promise.resolve({ ticket: 'ticket-xyz' }),
)
vi.mock('@/services/http', () => ({
  apiFetch: (path: string, init?: { method?: string }) => apiFetch(path, init),
}))

/**
 * Flushes the microtask queue so the async ticket fetch settles and the socket
 * is constructed. Works under fake timers because it only awaits microtasks.
 */
async function flushPromises(): Promise<void> {
  for (let i = 0; i < 5; i += 1) {
    await Promise.resolve()
  }
}

/** Minimal WebSocket double that records instances and exposes its callbacks. */
class MockWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn<() => void>(() => {
    this.readyState = MockWebSocket.CLOSED
  })

  constructor(readonly url: string) {
    MockWebSocket.instances.push(this)
  }

  open(): void {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }
}

/**
 * Returns the most recently constructed mock socket.
 *
 * @returns The latest {@link MockWebSocket} instance.
 */
function latestSocket(): MockWebSocket {
  const socket = MockWebSocket.instances[MockWebSocket.instances.length - 1]
  if (!socket) {
    throw new Error('No WebSocket was constructed')
  }
  return socket
}

beforeEach(() => {
  vi.stubGlobal('WebSocket', MockWebSocket)
  MockWebSocket.instances = []
  invalidateQueries.mockClear()
  getAccessToken.mockReturnValue('token-abc')
  apiFetch.mockClear()
  apiFetch.mockResolvedValue({ ticket: 'ticket-xyz' })
})

afterEach(async () => {
  // Reset the module-level singleton connection between tests.
  useRealtime().disconnect()
  await flushPromises()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useRealtime', () => {
  it('fetches a ticket and connects with it in the query, tracking status', async () => {
    const realtime = useRealtime()

    realtime.connect()
    expect(realtime.status.value).toBe('connecting')
    await flushPromises()

    expect(apiFetch).toHaveBeenCalledWith('/ws/ticket', { method: 'POST' })
    const socket = latestSocket()
    expect(socket.url).toBe('ws://backend.test/ws?ticket=ticket-xyz')

    socket.open()
    expect(realtime.status.value).toBe('open')
  })

  it('does not connect or fetch a ticket when there is no access token', async () => {
    getAccessToken.mockReturnValue(null)
    const realtime = useRealtime()

    realtime.connect()
    await flushPromises()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(MockWebSocket.instances).toHaveLength(0)
    expect(realtime.status.value).toBe('idle')
  })

  it('does not open a socket when the session ends while the ticket is in flight', async () => {
    let resolveTicket: (value: { ticket: string }) => void = () => {}
    apiFetch.mockReturnValueOnce(
      new Promise<{ ticket: string }>((resolve) => {
        resolveTicket = resolve
      }),
    )
    const realtime = useRealtime()

    realtime.connect()
    // Session ends before the ticket resolves.
    realtime.disconnect()
    resolveTicket({ ticket: 'ticket-late' })
    await flushPromises()

    expect(MockWebSocket.instances).toHaveLength(0)
    expect(realtime.status.value).toBe('idle')
  })

  it('dispatches events to subscribers and invalidates query keys', async () => {
    const realtime = useRealtime()
    const handler = vi.fn<(event: unknown) => void>()
    realtime.connect()
    await flushPromises()
    const socket = latestSocket()
    socket.open()

    const unsubscribe = realtime.on('NEW_ACTIVITY_NOTIFICATION', handler)
    socket.onmessage?.({
      data: JSON.stringify({ message: 'NEW_ACTIVITY_NOTIFICATION', notification_id: 9 }),
    })

    expect(handler).toHaveBeenCalledWith({
      message: 'NEW_ACTIVITY_NOTIFICATION',
      notification_id: 9,
    })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['notifications'] })

    unsubscribe()
    socket.onmessage?.({
      data: JSON.stringify({ message: 'NEW_ACTIVITY_NOTIFICATION', notification_id: 10 }),
    })
    expect(handler).toHaveBeenCalledTimes(1)
  })

  describe('data-changed hints', () => {
    /** Sends one hint over a freshly opened socket. */
    async function openSocket() {
      useRealtime().connect()
      await flushPromises()
      const socket = latestSocket()
      socket.open()
      return socket
    }

    function send(socket: ReturnType<typeof latestSocket>, message: string): void {
      socket.onmessage?.({ data: JSON.stringify({ message }) })
    }

    type Filter = { queryKey: unknown[]; predicate: (query: { queryKey: unknown[] }) => boolean }

    /** The invalidations asked for under one domain, e.g. `activities`. */
    function invalidationsOf(domain: string): Filter[] {
      return invalidateQueries.mock.calls
        .map(([filter]) => filter as Filter)
        .filter((filter) => filter.queryKey[0] === domain)
    }

    /** Which of the given keys an invalidation leaves alone, as its predicate sees them. */
    function keptAlone(filter: Filter | undefined, keys: unknown[][]): unknown[][] {
      return keys.filter((queryKey) => !filter?.predicate({ queryKey }))
    }

    it('refetches health data when a health sync finishes', async () => {
      send(await openSocket(), 'HEALTH_CHANGED')

      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['health'] })
    })

    it('refetches gears, but not the static component-type catalogue, when a gear sync finishes', async () => {
      send(await openSocket(), 'GEARS_CHANGED')

      expect(invalidateQueries).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['gears'] }),
      )
      expect(
        keptAlone(invalidationsOf('gears')[0], [
          ['gears', 'component-types'],
          ['gears', 'list', {}],
        ]),
      ).toEqual([['gears', 'component-types']])
    })

    it('refetches activity lists and stats for a new activity, but not other activities details', async () => {
      vi.useFakeTimers()
      const socket = await openSocket()

      send(socket, 'NEW_ACTIVITY_NOTIFICATION')
      await vi.advanceTimersByTimeAsync(1_000)

      const activityCalls = invalidationsOf('activities')
      expect(activityCalls).toHaveLength(1)
      expect(
        keptAlone(activityCalls[0], [
          ['activities', 'detail', 5, 'streams'],
          ['activities', 'exercise-titles'],
          ['activities', 'list', {}],
          ['activities', 'stats', 7, 'week'],
        ]),
      ).toEqual([
        ['activities', 'detail', 5, 'streams'],
        ['activities', 'exercise-titles'],
      ])
    })

    it('coalesces a burst of new-activity hints, as a bulk import sends, into one refetch', async () => {
      vi.useFakeTimers()
      const socket = await openSocket()

      for (let hint = 0; hint < 50; hint += 1) {
        send(
          socket,
          hint % 2 ? 'NEW_ACTIVITY_NOTIFICATION' : 'NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION',
        )
      }
      await vi.advanceTimersByTimeAsync(1_000)

      const activityCalls = invalidationsOf('activities')
      expect(activityCalls).toHaveLength(1)
    })

    it('refetches again for a hint that arrives after the burst settled', async () => {
      vi.useFakeTimers()
      const socket = await openSocket()

      send(socket, 'NEW_ACTIVITY_NOTIFICATION')
      await vi.advanceTimersByTimeAsync(1_000)
      send(socket, 'NEW_ACTIVITY_NOTIFICATION')
      await vi.advanceTimersByTimeAsync(1_000)

      const activityCalls = invalidationsOf('activities')
      expect(activityCalls).toHaveLength(2)
    })
  })

  describe('waiting on a background job', () => {
    async function openSocket() {
      useRealtime().connect()
      await flushPromises()
      const socket = latestSocket()
      socket.open()
      return socket
    }

    function hint(socket: ReturnType<typeof latestSocket>, job: string): void {
      socket.onmessage?.({ data: JSON.stringify({ message: 'JOB_STATUS_CHANGED', job }) })
    }

    /** Tracks whether a promise has settled, without awaiting it. */
    function track(promise: Promise<void>): { settled: boolean } {
      const state = { settled: false }
      void promise.then(() => {
        state.settled = true
      })
      return state
    }

    it('polls at the given interval while the socket is not open', async () => {
      vi.useFakeTimers()
      expect(jobPollInterval(1_500)).toBe(1_500)

      const wait = track(watchJob('garmin-link').wait(1_500))
      await vi.advanceTimersByTimeAsync(1_499)
      expect(wait.settled).toBe(false)
      await vi.advanceTimersByTimeAsync(1)
      expect(wait.settled).toBe(true)
    })

    it('polls slowly while the socket is open, since a hint announces the change', async () => {
      await openSocket()

      expect(jobPollInterval(1_500)).toBe(JOB_POLL_CONNECTED_MS)
      expect(jobPollInterval(1_500)).toBeGreaterThan(1_500)
    })

    it('never polls slower than the interval it was given', async () => {
      await openSocket()

      expect(jobPollInterval(30_000)).toBe(30_000)
    })

    it('waits the slow interval while connected, as the fallback for a lost hint', async () => {
      const socket = await openSocket()
      vi.useFakeTimers()
      const wait = track(watchJob('garmin-link').wait(1_500))
      expect(socket).toBeDefined()

      await vi.advanceTimersByTimeAsync(JOB_POLL_CONNECTED_MS - 1)
      expect(wait.settled).toBe(false)
      await vi.advanceTimersByTimeAsync(1)
      expect(wait.settled).toBe(true)
    })

    it('returns at once when a hint names the job it waits on', async () => {
      const socket = await openSocket()
      const wait = track(watchJob('garmin-link').wait(1_500))

      hint(socket, 'garmin-link')
      await flushPromises()

      expect(wait.settled).toBe(true)
    })

    it('ignores a hint for another job', async () => {
      const socket = await openSocket()
      const wait = track(watchJob('garmin-link').wait(1_500))

      hint(socket, 'strava:link')
      await flushPromises()

      expect(wait.settled).toBe(false)
    })

    it('remembers a hint that arrives between waits, so the next wait returns at once', async () => {
      const socket = await openSocket()
      const watch = watchJob('garmin-link')

      hint(socket, 'garmin-link')
      const wait = track(watch.wait(1_500))
      await flushPromises()

      expect(wait.settled).toBe(true)
    })

    it('waits normally again once a remembered hint has been used', async () => {
      const socket = await openSocket()
      const watch = watchJob('garmin-link')
      hint(socket, 'garmin-link')
      await watch.wait(1_500)

      const next = track(watch.wait(1_500))
      await flushPromises()

      expect(next.settled).toBe(false)
    })

    it('stops listening once stopped, so a later hint wakes nothing', async () => {
      const socket = await openSocket()
      const watch = watchJob('garmin-link')
      watch.stop()

      hint(socket, 'garmin-link')
      const wait = track(watch.wait(1_500))
      await flushPromises()

      expect(wait.settled).toBe(false)
    })
  })

  it('ignores malformed frames without throwing', async () => {
    const realtime = useRealtime()
    realtime.connect()
    await flushPromises()
    const socket = latestSocket()
    socket.open()
    invalidateQueries.mockClear()

    expect(() => socket.onmessage?.({ data: 'not-json' })).not.toThrow()
    expect(invalidateQueries).not.toHaveBeenCalled()
  })

  it('ignores a superseded socket closing, so the current connection keeps its status', async () => {
    vi.useFakeTimers()
    const realtime = useRealtime()
    realtime.connect()
    await flushPromises()
    const stale = latestSocket()
    // The server's close is in progress: the socket is closing but its close event has not fired.
    stale.readyState = MockWebSocket.CLOSING
    realtime.connect()
    await flushPromises()
    latestSocket().open()

    stale.onclose?.({ code: 1006 })
    vi.advanceTimersByTime(60_000)
    await flushPromises()

    expect(realtime.status.value).toBe('open')
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('ignores frames from a socket that was disconnected', async () => {
    const realtime = useRealtime()
    const handler = vi.fn<(event: unknown) => void>()
    realtime.connect()
    await flushPromises()
    const socket = latestSocket()
    socket.open()
    realtime.on('NEW_ACTIVITY_NOTIFICATION', handler)

    realtime.disconnect()
    socket.onmessage?.({ data: JSON.stringify({ message: 'NEW_ACTIVITY_NOTIFICATION' }) })

    expect(handler).not.toHaveBeenCalled()
  })

  it('reconnects with backoff after an unexpected close', async () => {
    vi.useFakeTimers()
    const realtime = useRealtime()
    realtime.connect()
    await flushPromises()
    const first = latestSocket()
    first.open()

    first.onclose?.({ code: 1006 })
    expect(realtime.status.value).toBe('closed')
    expect(MockWebSocket.instances).toHaveLength(1)

    // Backoff is 1s base + up to 30% jitter; advancing past it triggers a reconnect.
    vi.advanceTimersByTime(2_000)
    await flushPromises()
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('does not reconnect when the server evicts the connection', async () => {
    vi.useFakeTimers()
    const realtime = useRealtime()
    realtime.connect()
    await flushPromises()
    const first = latestSocket()
    first.open()

    first.onclose?.({ code: 4001 })
    vi.advanceTimersByTime(60_000)
    await flushPromises()

    expect(realtime.status.value).toBe('closed')
    expect(MockWebSocket.instances).toHaveLength(1)

    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()

    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('refetches notifications after both the initial connection and reconnect', async () => {
    vi.useFakeTimers()
    const realtime = useRealtime()
    realtime.connect()
    await flushPromises()
    const first = latestSocket()
    first.open()
    expect(invalidateQueries).toHaveBeenCalledTimes(1)
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['notifications'] })

    first.onclose?.({ code: 1006 })
    vi.advanceTimersByTime(2_000)
    await flushPromises()
    latestSocket().open()

    expect(invalidateQueries).toHaveBeenCalledTimes(2)
    expect(invalidateQueries).toHaveBeenNthCalledWith(2, { queryKey: ['notifications'] })
  })

  it('does not reconnect after an intentional disconnect', async () => {
    vi.useFakeTimers()
    const realtime = useRealtime()
    realtime.connect()
    await flushPromises()
    const socket = latestSocket()
    socket.open()

    realtime.disconnect()
    expect(socket.close).toHaveBeenCalled()
    expect(realtime.status.value).toBe('idle')

    vi.advanceTimersByTime(5_000)
    await flushPromises()
    expect(MockWebSocket.instances).toHaveLength(1)
  })
})
