import { storeToRefs } from 'pinia'
import { useQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { fetchEventLogSummary } from '@/features/eventLog/services/eventLog'

/** How often the live dashboard refetches while open (ms). */
const REFRESH_INTERVAL_MS = 30_000

/**
 * The event-log observability summary for a look-back window (admin scope).
 * Gated on authentication — the route guard already restricts the page to
 * admins. Refetches on an interval so the dashboard stays live, and re-runs
 * whenever the selected window changes.
 *
 * @param hours - Reactive look-back window in hours.
 * @returns The TanStack Query result for the event-log summary.
 */
export function useEventLogSummaryQuery(hours: Ref<number>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: computed(() => queryKeys.eventLog.summary(hours.value)),
    queryFn: ({ signal }) => fetchEventLogSummary(hours.value, signal),
    enabled: isAuthenticated,
    refetchInterval: REFRESH_INTERVAL_MS,
  })
}
