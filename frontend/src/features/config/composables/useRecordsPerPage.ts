import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import { queryKeys } from '@/services/queryKeys'
import {
  DEFAULT_PUBLIC_SERVER_SETTINGS,
  fetchPublicServerSettings,
} from '@/features/config/services/serverSettings'

/** Shared cache lifetime; server settings rarely change within a session. */
const SETTINGS_STALE_TIME = 5 * 60_000

/**
 * Exposes the server-enforced list page size (`num_records_per_page`) from the
 * public server settings. Shares the `public.serverSettings` query key, so it
 * reuses the same cached fetch the auth screens prime — no extra request when
 * settings are already warm — and falls back to the safe default while loading
 * or when the endpoint is unreachable.
 *
 * @returns A reactive `recordsPerPage` page size for paginated lists.
 */
export function useRecordsPerPage() {
  const query = useQuery({
    queryKey: queryKeys.public.serverSettings(),
    queryFn: fetchPublicServerSettings,
    placeholderData: DEFAULT_PUBLIC_SERVER_SETTINGS,
    staleTime: SETTINGS_STALE_TIME,
  })

  const recordsPerPage = computed(
    () =>
      query.data.value?.num_records_per_page ?? DEFAULT_PUBLIC_SERVER_SETTINGS.num_records_per_page,
  )

  return { recordsPerPage }
}
