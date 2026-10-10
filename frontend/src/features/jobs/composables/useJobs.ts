import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { fetchJobsSummary, replayJob } from '@/features/jobs/services/jobs'

/** How often the live dashboard refetches while open (ms). */
const REFRESH_INTERVAL_MS = 30_000

/**
 * The durable-jobs processing summary for a look-back window (admin scope).
 * Gated on authentication — the route guard already restricts the page to
 * admins. Refetches on an interval so the dashboard stays live, and re-runs
 * whenever the selected window changes.
 *
 * @param hours - Reactive look-back window in hours.
 * @returns The TanStack Query result for the jobs summary.
 */
export function useJobsSummaryQuery(hours: Ref<number>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: computed(() => queryKeys.jobs.summary(hours.value)),
    queryFn: ({ signal }) => fetchJobsSummary(hours.value, signal),
    enabled: isAuthenticated,
    refetchInterval: REFRESH_INTERVAL_MS,
  })
}

/**
 * Replays a dead-lettered job, then invalidates the jobs summary so the
 * dashboard reflects the requeue.
 *
 * @returns The TanStack mutation for replaying a job by id.
 */
export function useReplayJobMutation() {
  const client = useQueryClient()

  return useMutation<boolean, Error, string>({
    mutationFn: (jobId) => replayJob(jobId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.jobs.all() })
    },
  })
}
