import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'

import type { GearActivitiesPage } from '@/features/gears/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { GEAR_QUERY_STALE_TIME_MS } from '@/features/gears/constants'
import { fetchGearActivities } from '@/features/gears/services/gearActivities'

/**
 * One page of the activities recorded against a gear, driven by numbered
 * pagination. Keyed on gear id + page + size; uses `keepPreviousData` so paging
 * keeps the current rows visible until the next page resolves. Gated on a valid
 * gear id and authentication.
 *
 * @param gearId - The reactive parent gear id, or `null` when none is selected.
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @returns The TanStack Query result for the current activities page.
 */
export function useGearActivitiesQuery(
  gearId: MaybeRefOrGetter<number | null>,
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => toValue(gearId))

  return useQuery<GearActivitiesPage>({
    queryKey: computed(() =>
      queryKeys.gears.activities(id.value ?? -1, {
        page: toValue(page),
        numRecords: toValue(pageSize),
      }),
    ),
    queryFn: ({ signal }) =>
      fetchGearActivities(
        id.value as number,
        { page: toValue(page), numRecords: toValue(pageSize) },
        signal,
      ),
    staleTime: GEAR_QUERY_STALE_TIME_MS,
    placeholderData: keepPreviousData,
    enabled: computed(
      () => isAuthenticated.value && id.value !== null && Number.isFinite(id.value),
    ),
  })
}
