import type { Schemas } from '@/types'

/** Raw `EventLogSummary` payload from the backend. */
export type EventLogSummaryDto = Schemas['EventLogSummary']
/** Raw `EventTypeStats` payload from the backend. */
export type EventTypeStatsDto = Schemas['EventTypeStats']
/** Raw `EventLogPending` payload from the backend. */
export type EventLogPendingDto = Schemas['EventLogPending']
/** Raw `EventLogFailure` payload from the backend. */
export type EventLogFailureDto = Schemas['EventLogFailure']

/**
 * Per-event-type throughput, outcome, and latency counts.
 *
 * @property eventType - The domain-event channel.
 * @property total - Total events of this type in the window.
 * @property published - Count still in the published state.
 * @property processing - Count currently processing.
 * @property completed - Count that finished successfully.
 * @property failed - Count that failed.
 * @property deadLetter - Count moved to dead-letter.
 * @property avgProcessingTimeMs - Mean handler time, or `null` when unmeasured.
 * @property maxProcessingTimeMs - Slowest handler time, or `null`.
 */
export interface EventTypeStats {
  eventType: string
  total: number
  published: number
  processing: number
  completed: number
  failed: number
  deadLetter: number
  avgProcessingTimeMs: number | null
  maxProcessingTimeMs: number | null
}

/**
 * A group of not-yet-finished events and its oldest age.
 *
 * @property eventType - The domain-event channel.
 * @property status - The pending state (`published` or `processing`).
 * @property count - Number of events in this group.
 * @property oldestSeconds - Age of the oldest event, in seconds.
 */
export interface EventLogPending {
  eventType: string
  status: string
  count: number
  oldestSeconds: number | null
}

/**
 * A single failed or dead-lettered event for inspection.
 *
 * @property id - The event id.
 * @property eventType - The domain-event channel.
 * @property eventSource - Where the event originated.
 * @property handlerName - The subscriber(s) that processed the event.
 * @property errorMessage - The failure reason.
 * @property retryCount - Processing attempts so far.
 * @property eventMetadata - Correlation context (request_id, user_id, activity_id).
 * @property createdAt - When the event was published.
 * @property completedAt - When processing finished.
 */
export interface EventLogFailure {
  id: string
  eventType: string
  eventSource: string
  handlerName: string | null
  errorMessage: string | null
  retryCount: number
  eventMetadata: Record<string, unknown> | null
  createdAt: string
  completedAt: string | null
}

/**
 * The full admin-dashboard payload, aggregated from the backend `event_log`.
 *
 * @property windowHours - The look-back window applied to the aggregates.
 * @property totalEvents - Total events recorded within the window.
 * @property byType - Per-event-type throughput/outcome/latency stats.
 * @property pending - Not-yet-finished event groups and their oldest age.
 * @property recentFailures - The most recent failed/dead-lettered events.
 */
export interface EventLogSummary {
  windowHours: number
  totalEvents: number
  byType: EventTypeStats[]
  pending: EventLogPending[]
  recentFailures: EventLogFailure[]
}
