import type { Schemas } from '@/types'

/** Raw `JobsSummary` payload from the backend. */
export type JobsSummaryDto = Schemas['JobsSummary']
/** Raw `JobSubscriberStats` payload from the backend. */
export type JobSubscriberStatsDto = Schemas['JobSubscriberStats']
/** Raw `DeadLetterJob` payload from the backend. */
export type DeadLetterJobDto = Schemas['DeadLetterJob']

/**
 * Per-subscriber durable-job counts by status within the window.
 *
 * @property subscriberId - The durable subscriber.
 * @property eventType - The event channel it reacts to.
 * @property total - Total jobs for this subscriber in the window.
 * @property pending - Count waiting to be claimed (includes backoff).
 * @property claimed - Count currently leased by a worker.
 * @property completed - Count that finished successfully.
 * @property deadLetter - Count that exhausted retries.
 */
export interface JobSubscriberStats {
  subscriberId: string
  eventType: string
  total: number
  pending: number
  claimed: number
  completed: number
  deadLetter: number
}

/**
 * A dead-lettered job, shown for inspection and replay.
 *
 * @property id - The job id (used to replay it).
 * @property eventId - The originating envelope event id.
 * @property eventType - The event channel.
 * @property subscriberId - The subscriber that failed.
 * @property source - Where the originating event came from.
 * @property attempts - Attempts made before dead-lettering.
 * @property maxAttempts - The attempt ceiling that was reached.
 * @property lastError - The final failure reason.
 * @property createdAt - When the job was enqueued.
 * @property updatedAt - When the job was dead-lettered.
 * @property completedAt - When the job reached its terminal state.
 */
export interface DeadLetterJob {
  id: string
  eventId: string
  eventType: string
  subscriberId: string
  source: string
  attempts: number
  maxAttempts: number
  lastError: string | null
  createdAt: string
  updatedAt: string
  completedAt: string | null
}

/**
 * The durable-jobs admin-dashboard payload.
 *
 * @property windowHours - The look-back window applied to the counts.
 * @property totalJobs - Total jobs enqueued within the window.
 * @property pending - Window count waiting to be claimed.
 * @property claimed - Window count currently leased.
 * @property completed - Window count finished successfully.
 * @property deadLetter - Window count that exhausted retries.
 * @property oldestPendingSeconds - Age of the oldest unfinished job, in seconds.
 * @property bySubscriber - Per-subscriber breakdown within the window.
 * @property recentDeadLetter - The current dead-letter queue contents.
 */
export interface JobsSummary {
  windowHours: number
  totalJobs: number
  pending: number
  claimed: number
  completed: number
  deadLetter: number
  oldestPendingSeconds: number | null
  bySubscriber: JobSubscriberStats[]
  recentDeadLetter: DeadLetterJob[]
}
