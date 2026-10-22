import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useRealtime } from '@/composables/useRealtime'

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

  it('ignores malformed frames without throwing', async () => {
    const realtime = useRealtime()
    realtime.connect()
    await flushPromises()
    const socket = latestSocket()
    socket.open()

    expect(() => socket.onmessage?.({ data: 'not-json' })).not.toThrow()
    expect(invalidateQueries).not.toHaveBeenCalled()
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

  it('refetches notifications when the socket reopens after a drop, not on the first open', async () => {
    vi.useFakeTimers()
    const realtime = useRealtime()
    realtime.connect()
    await flushPromises()
    const first = latestSocket()
    first.open()
    expect(invalidateQueries).not.toHaveBeenCalled()

    first.onclose?.({ code: 1006 })
    vi.advanceTimersByTime(2_000)
    await flushPromises()
    latestSocket().open()

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['notifications'] })
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
