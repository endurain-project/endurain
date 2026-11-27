import type { QueryClient } from '@tanstack/vue-query'

import { watchJob } from '@/composables/useRealtime'
import { apiFetch, HttpError } from '@/services/http'
import { queryKeys } from '@/services/queryKeys'
import type { Schemas } from '@/types'

/** Where a background job is; every status read the backend answers for a job uses it. */
export type JobState = Schemas['JobState']

/** What a background job does. */
export type JobKind = Schemas['JobKind']

/** Any background job, as `GET /jobs/{id}` answers it; narrow it on `kind`. */
export type Job = Schemas['JobPage']['items'][number]

/**
 * The job variants whose `kind` admits `K`. A variant can cover several kinds (the activity jobs
 * share one), and the default `JobKind` gives every variant.
 */
export type JobOf<K extends JobKind> = Job extends infer Variant
  ? Variant extends { kind: infer Kinds }
    ? [Extract<K, Kinds>] extends [never]
      ? never
      : Variant
    : never
  : never

/**
 * Whether a job is of the given kind, narrowing it to that kind's variant.
 *
 * @param job - Any job.
 * @param kind - The kind to check for.
 * @returns `true` when the job's `kind` is `kind`.
 */
export function isJobOf<K extends JobKind>(job: Job, kind: K): job is JobOf<K> {
  return job.kind === kind
}

/** A keyset slice of the caller's jobs, newest first. */
export type JobPage = Schemas['JobPage']

/** Filters and paging for {@link listJobs}. */
export interface ListJobsParams {
  kind?: JobKind
  status?: JobState
  cursor?: string
  numRecords?: number
}

/** The states a job does not leave, so polling can stop. */
export const TERMINAL_JOB_STATES: readonly JobState[] = ['succeeded', 'failed']

/** How often {@link followJob} reads a job when no interval is given. */
const FOLLOW_INTERVAL_MS = 1_500

/** How long {@link followJob} follows a job when no timeout is given. */
const FOLLOW_TIMEOUT_MS = 5 * 60 * 1_000

/**
 * Reads the running job a start route's `409` names, so the caller can follow it instead of
 * starting another.
 *
 * @param error - What a start request threw.
 * @returns The running job's id, or `null` when the error is not a `409` that names one (an older
 *   server, or an `Idempotency-Key` reused for a different request).
 */
export function runningJobId(error: unknown): string | null {
  return error instanceof HttpError && error.status === 409 ? error.jobId : null
}

/**
 * Whether a job has reached a state it will not leave.
 *
 * @param state - The job's `status`.
 * @returns `true` when the job succeeded or failed.
 */
export function isTerminalJobState(state: JobState): boolean {
  return TERMINAL_JOB_STATES.includes(state)
}

/**
 * Raised when {@link followJob} gives up on a job that is still running. The job may still finish
 * server-side; only the client stopped watching.
 */
export class JobTimeoutError extends Error {
  constructor() {
    super('Timed out waiting for the background job to finish.')
    this.name = 'JobTimeoutError'
  }
}

/**
 * Reads one of the caller's background jobs.
 *
 * @param id - The job id the request that started it returned.
 * @param signal - Optional abort signal for cancellation.
 * @returns The job's current state.
 * @throws {HttpError} `404` when the id is unknown, expired or belongs to another user.
 */
export function fetchJob<K extends JobKind = JobKind>(
  id: string,
  signal?: AbortSignal,
): Promise<JobOf<K>> {
  return apiFetch<JobOf<K>>(`/jobs/${encodeURIComponent(id)}`, { signal })
}

/**
 * Lists the caller's own background jobs, newest first.
 *
 * @param params - Optional kind and status filters, and the cursor and page size.
 * @param signal - Optional abort signal for cancellation.
 * @returns One page of jobs with the cursor of the next.
 * @throws {HttpError} When the request fails.
 */
export function listJobs(params: ListJobsParams = {}, signal?: AbortSignal): Promise<JobPage> {
  const query = new URLSearchParams()
  if (params.kind) {
    query.set('kind', params.kind)
  }
  if (params.status) {
    query.set('status', params.status)
  }
  if (params.cursor) {
    query.set('cursor', params.cursor)
  }
  if (params.numRecords !== undefined) {
    query.set('num_records', String(params.numRecords))
  }
  const search = query.toString()
  return apiFetch<JobPage>(search ? `/jobs?${search}` : '/jobs', { signal })
}

/**
 * Follows a job until it finishes. A realtime hint for the job ends a wait early; otherwise the
 * job is read every `intervalMs` (slower while the socket is open, see `jobPollInterval`). Start
 * it right after the 202 that returned the id.
 *
 * @param id - The job id.
 * @param options - Abort signal, the interval between reads, and how long to follow.
 * @returns The finished job, succeeded or failed; the caller decides what a failure means.
 * @throws {JobTimeoutError} When the job is still running at the deadline.
 * @throws {HttpError} When a read fails.
 * @throws The signal's reason when it aborts.
 */
export async function followJob<K extends JobKind = JobKind>(
  id: string,
  options: { signal?: AbortSignal; intervalMs?: number; timeoutMs?: number } = {},
): Promise<JobOf<K>> {
  const intervalMs = options.intervalMs ?? FOLLOW_INTERVAL_MS
  const deadline = Date.now() + (options.timeoutMs ?? FOLLOW_TIMEOUT_MS)
  const watch = watchJob(id)
  try {
    for (;;) {
      options.signal?.throwIfAborted()
      const job = await fetchJob<K>(id, options.signal)
      if (isTerminalJobState(job.status)) {
        return job
      }
      if (Date.now() >= deadline) {
        throw new JobTimeoutError()
      }
      await watch.wait(intervalMs)
    }
  } finally {
    watch.stop()
  }
}

/**
 * Puts a job a 202 returned into the cache, so a query that follows it starts from that state and
 * a screen that looks up the latest job of its kind sees it at once.
 *
 * @param client - The active query client.
 * @param job - The job body of the 202.
 */
export function seedJob(client: QueryClient, job: Job): void {
  client.setQueryData(queryKeys.jobs.detail(job.id), job)
  client.setQueryData(queryKeys.jobs.latest(job.kind), job)
}

/**
 * Looks the latest job of a kind up again when a start request was refused because that job is
 * already running, so a screen that follows the latest job of its kind picks the running one up.
 *
 * @param client - The active query client.
 * @param kind - The kind of job the request started.
 * @param error - What the start request threw.
 */
export function refreshLatestJobOnConflict(
  client: QueryClient,
  kind: JobKind,
  error: unknown,
): void {
  if (runningJobId(error) !== null) {
    void client.invalidateQueries({ queryKey: queryKeys.jobs.latest(kind) })
  }
}
