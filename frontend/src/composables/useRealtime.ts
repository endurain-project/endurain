import { readonly, ref } from 'vue'

import { invalidateExcept } from '@/composables/useInvalidatingMutation'
import { queryClient } from '@/plugins/vueQuery'
import { getAccessToken } from '@/services/authTokens'
import { apiFetch } from '@/services/http'
import { ACTIVITY_ROW_INDEPENDENT_KEYS, queryKeys } from '@/services/queryKeys'
import { getWebSocketUrl } from '@/services/runtime'

import { useTelemetry } from './useTelemetry'

/** Connection state of the realtime channel. */
export type RealtimeStatus = 'idle' | 'connecting' | 'open' | 'closed'

/**
 * A parsed realtime frame. The backend tags every message with a `message`
 * discriminator; additional fields vary per event type.
 */
export interface RealtimeEvent {
  message: string
  [key: string]: unknown
}

/** Handler invoked for a subscribed realtime event. */
export type RealtimeHandler = (event: RealtimeEvent) => void

/**
 * How often a background job is checked while the socket is open. The server announces the
 * job's change, so the check is only the fallback for a hint that never arrives (it is
 * best-effort): the longest a user can wait for a lost hint.
 */
export const JOB_POLL_CONNECTED_MS = 5_000

const RECONNECT_BASE_MS = 1_000
const RECONNECT_MAX_MS = 30_000
const RECONNECT_JITTER_RATIO = 0.3
// Close code the server sends to a connection pushed out by a newer one (more tabs than it
// allows). Reconnecting would evict another tab in turn, so the loop would never settle.
const EVICTED_CLOSE_CODE = 4001

/** A cache invalidation a realtime event triggers. */
interface Invalidation {
  /** The domain prefix to invalidate. */
  queryKey: readonly unknown[]
  /** Key prefixes under `queryKey` the event cannot have changed. */
  excludeKeys?: ReadonlyArray<readonly unknown[]>
  /** Run at most once per this many milliseconds, for events that arrive in bursts. */
  coalesceMs?: number
}

const NOTIFICATIONS: Invalidation = { queryKey: queryKeys.notifications.all() }

/**
 * A stored activity changes the lists, feeds, stats and summaries. A bulk import announces one
 * activity at a time, so the refetch is coalesced instead of restarting for every one.
 */
const ACTIVITIES: Invalidation = {
  queryKey: queryKeys.activities.all(),
  excludeKeys: ACTIVITY_ROW_INDEPENDENT_KEYS,
  coalesceMs: 1_000,
}

/** A provider gear sync changes the gears; the component-type catalogue is static. */
const GEARS: Invalidation = {
  queryKey: queryKeys.gears.all(),
  excludeKeys: [queryKeys.gears.componentTypes()],
}

const HEALTH: Invalidation = { queryKey: queryKeys.health.all() }

/**
 * Invalidations to run when a realtime event arrives, so server push keeps
 * TanStack Query caches fresh without manual refetching. Keys come from the
 * central {@link queryKeys} factory so an invalidation can never drift from the
 * key a query registers under. Extend this map as views adopt realtime-backed
 * queries; invalidating a key with no active query is a harmless no-op.
 */
const EVENT_QUERY_INVALIDATIONS: Record<string, ReadonlyArray<Invalidation>> = {
  NEW_ACTIVITY_NOTIFICATION: [NOTIFICATIONS, ACTIVITIES],
  NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION: [NOTIFICATIONS, ACTIVITIES],
  NEW_FOLLOWER_REQUEST_NOTIFICATION: [NOTIFICATIONS],
  NEW_FOLLOWER_REQUEST_REMOVED_NOTIFICATION: [NOTIFICATIONS],
  NEW_FOLLOWER_REQUEST_ACCEPTED_NOTIFICATION: [NOTIFICATIONS],
  ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_NOTIFICATION: [NOTIFICATIONS],
  GARMIN_TOKEN_EXPIRED_NOTIFICATION: [NOTIFICATIONS],
  STRAVA_TOKEN_EXPIRED_NOTIFICATION: [NOTIFICATIONS],
  GEARS_CHANGED: [GEARS],
  HEALTH_CHANGED: [HEALTH],
}

// Module-level state guarantees a single connection per browser tab regardless
// of how many components call useRealtime().
const status = ref<RealtimeStatus>('idle')
const handlers = new Map<string, Set<RealtimeHandler>>()
let socket: WebSocket | null = null
let reconnectAttempts = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let intentionalClose = false
// Set when the server evicted this tab's connection; the tab reconnects once it is visible again.
let evicted = false
// Guards against overlapping ticket fetches while a connection is being opened.
let connecting = false
// Coalesced invalidations waiting for their window to end.
const pendingInvalidations = new Map<Invalidation, ReturnType<typeof setTimeout>>()

/**
 * Runs an invalidation, or schedules it once when it is coalesced and one is already waiting.
 *
 * @param invalidation - The invalidation a realtime event triggers.
 */
function invalidate(invalidation: Invalidation): void {
  const run = () => {
    if (invalidation.excludeKeys) {
      void invalidateExcept(queryClient, invalidation.queryKey, invalidation.excludeKeys)
    } else {
      void queryClient.invalidateQueries({ queryKey: invalidation.queryKey })
    }
  }
  if (!invalidation.coalesceMs) {
    run()
  } else if (!pendingInvalidations.has(invalidation)) {
    pendingInvalidations.set(
      invalidation,
      setTimeout(() => {
        pendingInvalidations.delete(invalidation)
        run()
      }, invalidation.coalesceMs),
    )
  }
}

/**
 * Routes a parsed frame to its query invalidations and subscribed handlers.
 *
 * @param event - The parsed realtime event.
 */
function dispatch(event: RealtimeEvent): void {
  for (const invalidation of EVENT_QUERY_INVALIDATIONS[event.message] ?? []) {
    invalidate(invalidation)
  }
  for (const handler of Array.from(handlers.get(event.message) ?? [])) {
    handler(event)
  }
}

/**
 * Cancels any pending reconnect attempt.
 */
function clearReconnectTimer(): void {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

/**
 * Schedules a reconnect with exponential backoff and jitter, unless the socket
 * was closed intentionally or a reconnect is already pending.
 */
function scheduleReconnect(): void {
  if (intentionalClose || reconnectTimer !== null) {
    return
  }
  const backoff = Math.min(RECONNECT_BASE_MS * 2 ** reconnectAttempts, RECONNECT_MAX_MS)
  const delay = backoff + Math.random() * RECONNECT_JITTER_RATIO * backoff
  reconnectAttempts += 1
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    void openSocket()
  }, delay)
}

/**
 * Requests a short-lived, single-use WebSocket ticket from the backend. The
 * ticket authenticates the handshake so the access token never appears in a
 * URL. Routed through {@link apiFetch}, so it carries the bearer token and the
 * CSRF header automatically.
 *
 * @returns The opaque ticket string.
 */
async function fetchTicket(): Promise<string> {
  const { ticket } = await apiFetch<{ ticket: string }>('/ws/ticket', { method: 'POST' })
  return ticket
}

/**
 * Opens the WebSocket. Fetches a single-use ticket first, then connects with
 * `?ticket=`. No-ops when unauthenticated or when a connection is already
 * open, connecting, or mid-handshake.
 */
async function openSocket(): Promise<void> {
  if (!getAccessToken()) {
    // No session yet; a post-login connect() will start the socket.
    status.value = 'idle'
    return
  }
  if (
    connecting ||
    (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING))
  ) {
    return
  }

  intentionalClose = false
  connecting = true
  status.value = 'connecting'

  let ticket: string
  try {
    ticket = await fetchTicket()
  } catch (error) {
    connecting = false
    useTelemetry().captureError(error, { scope: 'realtime.ticket' })
    // A logout clears the token, so the retried attempt short-circuits to idle.
    scheduleReconnect()
    return
  }

  // The session may have ended (logout) while the ticket request was in flight.
  if (intentionalClose || !getAccessToken()) {
    connecting = false
    if (intentionalClose) {
      status.value = 'idle'
    }
    return
  }

  let next: WebSocket
  try {
    const url = `${getWebSocketUrl()}?ticket=${encodeURIComponent(ticket)}`
    next = new WebSocket(url)
  } catch (error) {
    connecting = false
    useTelemetry().captureError(error, { scope: 'realtime.open' })
    scheduleReconnect()
    return
  }
  socket = next
  connecting = false

  next.onopen = () => {
    reconnectAttempts = 0
    status.value = 'open'
    evicted = false
    // Hints sent before the first connection or while it was down are not replayed.
    void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all() })
  }
  next.onmessage = (event: MessageEvent) => {
    try {
      const data = JSON.parse(String(event.data)) as RealtimeEvent
      if (data && typeof data.message === 'string') {
        dispatch(data)
      }
    } catch (error) {
      useTelemetry().captureError(error, { scope: 'realtime.message' })
    }
  }
  next.onclose = (event: CloseEvent) => {
    socket = null
    status.value = 'closed'
    if (event.code === EVICTED_CLOSE_CODE) {
      evicted = true
    } else {
      scheduleReconnect()
    }
  }
}

// An evicted tab stays closed while hidden; showing it again is the user's signal that it wants live updates.
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && evicted && !intentionalClose) {
      evicted = false
      void openSocket()
    }
  })
}

/**
 * Subscribes a handler to a named realtime event.
 *
 * @param event - The backend event name (the frame's `message` value).
 * @param handler - Callback invoked with each matching event.
 * @returns An unsubscribe function.
 */
function subscribe(event: string, handler: RealtimeHandler): () => void {
  const set = handlers.get(event) ?? new Set<RealtimeHandler>()
  set.add(handler)
  handlers.set(event, set)
  return () => {
    set.delete(handler)
    if (set.size === 0) {
      handlers.delete(event)
    }
  }
}

/**
 * How long to wait between checks of a background job's status.
 *
 * While the socket is open the server announces the job's change, so the check slows to
 * {@link JOB_POLL_CONNECTED_MS}; without the socket nothing would announce it, so it keeps
 * the given interval. Never longer than the interval given.
 *
 * @param fastMs - The interval to use when no hint can arrive.
 * @returns The interval to wait.
 */
export function jobPollInterval(fastMs: number): number {
  return status.value === 'open' ? Math.max(fastMs, JOB_POLL_CONNECTED_MS) : fastMs
}

/** A follow of one background job's hints; see {@link watchJob}. */
export interface JobWatch {
  /**
   * Waits until it is time to check the job's status again: the poll interval
   * ({@link jobPollInterval}) passes, or a hint for the job has arrived, including one that
   * arrived since the last wait.
   *
   * @param fastMs - The interval to use when no hint can arrive.
   * @returns A promise that resolves when the job should be checked.
   */
  wait: (fastMs: number) => Promise<void>
  /** Stops listening for the job's hints. */
  stop: () => void
}

/**
 * Follows the server's `JOB_STATUS_CHANGED` hints for one background job. Start it before the
 * request that reads or starts the job: a hint that arrives while that request is in flight is
 * remembered and ends the next {@link JobWatch.wait} at once, instead of being lost.
 *
 * @param job - The job's name, as the server's hint carries it.
 * @returns The watch; call `stop` when the job is done.
 */
export function watchJob(job: string): JobWatch {
  let hinted = false
  let wake: (() => void) | null = null
  const unsubscribe = subscribe('JOB_STATUS_CHANGED', (event) => {
    if (event.job === job) {
      hinted = true
      wake?.()
    }
  })
  return {
    wait: (fastMs) => {
      if (hinted) {
        hinted = false
        return Promise.resolve()
      }
      return new Promise((resolve) => {
        const done = () => {
          clearTimeout(timer)
          hinted = false
          wake = null
          resolve()
        }
        const timer = setTimeout(done, jobPollInterval(fastMs))
        wake = done
      })
    },
    stop: unsubscribe,
  }
}

/**
 * Single-connection realtime channel over the backend WebSocket. Manages one
 * connection per tab with automatic reconnection (exponential backoff + jitter),
 * dispatches typed events to subscribers, and invalidates the relevant
 * TanStack Query keys so the cache stays fresh from server push.
 *
 * Components subscribe to event *names* via {@link on} rather than touching raw
 * socket frames, so the transport can evolve without changing call sites.
 *
 * @returns The reactive connection status plus connect, disconnect, and
 *   subscribe helpers.
 */
export function useRealtime() {
  /**
   * Connects (or reconnects) the realtime channel. Safe to call repeatedly;
   * a connection that is already open is reused.
   */
  function connect(): void {
    intentionalClose = false
    void openSocket()
  }

  /**
   * Closes the realtime channel and stops reconnecting. Call on logout.
   */
  function disconnect(): void {
    intentionalClose = true
    evicted = false
    clearReconnectTimer()
    reconnectAttempts = 0
    for (const timer of pendingInvalidations.values()) {
      clearTimeout(timer)
    }
    pendingInvalidations.clear()
    if (socket) {
      // Detach onclose first so closing doesn't schedule a reconnect.
      socket.onclose = null
      socket.close()
      socket = null
    }
    status.value = 'idle'
  }

  /**
   * Subscribes a handler to a named realtime event.
   *
   * @param event - The backend event name (the frame's `message` value).
   * @param handler - Callback invoked with each matching event.
   * @returns An unsubscribe function.
   */
  function on(event: string, handler: RealtimeHandler): () => void {
    return subscribe(event, handler)
  }

  return { status: readonly(status), connect, disconnect, on }
}
