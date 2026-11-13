import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  type ActivityListFilters,
  type ActivitySortBy,
  type ActivitySortOrder,
  fetchUserActivitiesPage,
  fetchUserActivityTypes,
} from '@/features/activities/services/activities'

/** Resolves a reactive user id to its string, or `''` when unavailable. */
function resolveUserId(userId: MaybeRefOrGetter<string | null>): string {
  return toValue(userId) ?? ''
}

/**
 * One filtered, sorted page of the authenticated user's own activities, backing
 * the activities list view. Keyed on the owner, page, size, every filter, and
 * the sort so each distinct query caches independently; uses `keepPreviousData`
 * so paging and filtering keep the current rows visible until the next page
 * resolves (no flash of empty state). Gated on a valid user id and auth.
 *
 * @param userId - Reactive id of the list owner (the authenticated viewer).
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @param filters - Reactive server-side filters (type, dates, name search).
 * @param sortBy - Reactive sort column.
 * @param sortOrder - Reactive sort direction.
 * @returns The TanStack query result for the current activities page.
 */
export function useUserActivitiesQuery(
  userId: MaybeRefOrGetter<string | null>,
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  filters: MaybeRefOrGetter<ActivityListFilters>,
  sortBy: MaybeRefOrGetter<ActivitySortBy>,
  sortOrder: MaybeRefOrGetter<ActivitySortOrder>,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery({
    queryKey: computed(() =>
      queryKeys.activities.list({
        scope: 'user-list',
        userId: id.value,
        page: toValue(page),
        numRecords: toValue(pageSize),
        filters: toValue(filters),
        sortBy: toValue(sortBy),
        sortOrder: toValue(sortOrder),
      }),
    ),
    queryFn: ({ signal }) =>
      fetchUserActivitiesPage(
        {
          userId: id.value,
          page: toValue(page),
          numRecords: toValue(pageSize),
          filters: toValue(filters),
          sortBy: toValue(sortBy),
          sortOrder: toValue(sortOrder),
        },
        signal,
      ),
    placeholderData: keepPreviousData,
    enabled: computed(() => isAuthenticated.value && id.value !== ''),
  })
}

/**
 * The distinct activity types the authenticated user owns, powering the activity-type
 * filters so they only offer types the user has; gated on authentication.
 *
 * @returns The TanStack query result for the user's activity types.
 */
export function useUserActivityTypesQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.activities.types(),
    queryFn: ({ signal }) => fetchUserActivityTypes(signal),
    enabled: isAuthenticated,
  })
}
