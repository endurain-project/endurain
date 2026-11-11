import { computed, onScopeDispose, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import { isJobHintFor, jobPollInterval, useRealtime } from '@/composables/useRealtime'
import { HttpError } from '@/services/http'
import {
  fetchJob,
  isJobOf,
  isTerminalJobState,
  listJobs,
  type JobKind,
  type JobOf,
} from '@/services/jobStatus'
import { queryKeys } from '@/services/queryKeys'

/**
 * Follows one background job until it reaches a terminal state. While the realtime channel is
 * open the server announces each change of the job, which re-reads it at once, and the poll only
 * backs that up; without the channel it polls at `intervalMs`. It keeps polling in a background
 * tab, because the user may be waiting on another app (an MFA code). Seed the cache from the 202
 * body with `seedJob` so the first render needs no read.
 *
 * @param id - The job id, or `null` while there is none to follow.
 * @param options - `intervalMs`: the poll interval when no hint can arrive.
 * @returns The TanStack Query result; `data` is the job's current state.
 */
export function useJobQuery<K extends JobKind = JobKind>(
  id: MaybeRefOrGetter<string | null>,
  options: { intervalMs: number },
) {
  const query = useQuery<JobOf<K>, Error>({
    queryKey: computed(() => queryKeys.jobs.detail(toValue(id) ?? '')),
    queryFn: ({ signal }) => fetchJob<K>(toValue(id) as string, signal),
    enabled: computed(() => toValue(id) !== null),
    retry: false,
    refetchInterval: (state) => {
      // An unknown or expired id stays unknown; polling it would only repeat the 404.
      if (state.state.error instanceof HttpError && state.state.error.status === 404) {
        return false
      }
      const job = state.state.data
      return job && isTerminalJobState(job.status) ? false : jobPollInterval(options.intervalMs)
    },
    refetchIntervalInBackground: true,
  })
  const stopListening = useRealtime().on('JOB_STATUS_CHANGED', (event) => {
    const jobId = toValue(id)
    if (jobId !== null && isJobHintFor(event, jobId)) {
      void query.refetch()
    }
  })
  onScopeDispose(stopListening)
  return query
}

/**
 * Finds the caller's newest job of one kind, so a screen can show a job that was started before
 * the page loaded (a reload, another tab). Follow the job it finds with {@link useJobQuery}.
 *
 * @param kind - What the job does.
 * @returns The TanStack Query result; `data` is the newest job, or `null` when there is none.
 */
export function useLatestJobQuery<K extends JobKind>(kind: K) {
  return useQuery<JobOf<K> | null, Error>({
    queryKey: queryKeys.jobs.latest(kind),
    queryFn: async ({ signal }) => {
      const page = await listJobs({ kind, numRecords: 1 }, signal)
      // The list is filtered by kind on the server; the check narrows the type and drops nothing.
      return page.items.find((job): job is JobOf<K> => isJobOf(job, kind)) ?? null
    },
  })
}
