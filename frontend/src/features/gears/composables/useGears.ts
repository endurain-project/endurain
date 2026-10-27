import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'

import type { Gear, GearDetail, GearInput } from '@/features/gears/types'

import { queryKeys } from '@/services/queryKeys'
import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { useAuthStore } from '@/features/auth/stores/auth'
import { GEAR_QUERY_STALE_TIME_MS } from '@/features/gears/constants'
import {
  createGear,
  deleteGear,
  fetchGearById,
  fetchGears,
  searchGearsByNickname,
  updateGear,
} from '@/features/gears/services/gears'

/**
 * One page of the authenticated user's gears, driven by numbered pagination so
 * the page size honours the server's `num_records_per_page` setting (see
 * `useRecordsPerPage`). Keyed on page + size + the show-inactive filter; uses
 * `keepPreviousData` so paging keeps the current rows visible until the next
 * page resolves (no flash of empty state). Gated on authentication.
 *
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @param showInactive - Reactive flag controlling whether inactive gears show.
 * @returns The TanStack query result for the current gears page.
 */
export function useGearsQuery(
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  showInactive: MaybeRefOrGetter<boolean>,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: computed(() =>
      queryKeys.gears.list({
        page: toValue(page),
        numRecords: toValue(pageSize),
        showInactive: toValue(showInactive),
      }),
    ),
    queryFn: ({ signal }) =>
      fetchGears(
        {
          page: toValue(page),
          numRecords: toValue(pageSize),
          showInactive: toValue(showInactive),
        },
        signal,
      ),
    staleTime: GEAR_QUERY_STALE_TIME_MS,
    placeholderData: keepPreviousData,
    enabled: isAuthenticated,
  })
}

/**
 * Nickname "contains" search. Enabled only once the (debounced) term is
 * non-empty so an empty box never fires a request; gated on authentication.
 *
 * @param term - The reactive (debounced) search term.
 * @returns The TanStack Query result for the matching gears.
 */
export function useGearSearchQuery(term: MaybeRefOrGetter<string>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const trimmed = computed(() => toValue(term).trim())

  return useQuery<Gear[]>({
    queryKey: computed(() => queryKeys.gears.search(trimmed.value)),
    queryFn: ({ signal }) => searchGearsByNickname(trimmed.value, signal),
    staleTime: GEAR_QUERY_STALE_TIME_MS,
    enabled: computed(() => isAuthenticated.value && trimmed.value.length > 0),
  })
}

/**
 * Single gear detail (with computed stats). Gated on a valid id and auth.
 *
 * @param id - The reactive gear id, or `null` when none is selected.
 * @returns The TanStack Query result for the gear detail.
 */
export function useGearQuery(id: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const gearId = computed(() => toValue(id))

  return useQuery<GearDetail | null>({
    queryKey: computed(() => queryKeys.gears.detail(gearId.value ?? -1)),
    queryFn: ({ signal }) => fetchGearById(gearId.value as number, signal),
    staleTime: GEAR_QUERY_STALE_TIME_MS,
    enabled: computed(
      () => isAuthenticated.value && gearId.value !== null && Number.isFinite(gearId.value),
    ),
  })
}

/**
 * What a write to a gear itself cannot change: its components, the static
 * component-type catalogue and the activity rows it is attached to. Excluded from
 * the gears invalidation so editing a gear does not refetch them.
 */
const GEAR_WRITE_UNAFFECTED_KEYS = [
  queryKeys.gears.componentsLists(),
  queryKeys.gears.componentTypes(),
  queryKeys.gears.activitiesLists(),
] as const

/**
 * Create mutation. Invalidation-based per the mutation reference: on settle it
 * invalidates the gears domain, so every list, the nickname search, the pickers
 * and any detail view refetch the server-authoritative state.
 *
 * @returns The TanStack Query mutation for creating a gear.
 */
export function useCreateGearMutation() {
  return useInvalidatingMutation<Gear, GearInput>({
    mutationKey: queryKeys.gears.all(),
    excludeKeys: GEAR_WRITE_UNAFFECTED_KEYS,
    mutationFn: (input) => createGear(input),
  })
}

/**
 * Update mutation. Invalidates the gears domain on settle.
 *
 * @returns The TanStack Query mutation for updating a gear.
 */
export function useUpdateGearMutation() {
  return useInvalidatingMutation<Gear, { id: number; input: GearInput; version: number }>({
    mutationKey: queryKeys.gears.all(),
    excludeKeys: GEAR_WRITE_UNAFFECTED_KEYS,
    mutationFn: ({ id, input, version }) => updateGear(id, input, version),
  })
}

/**
 * Delete mutation. Invalidates the gears domain on settle.
 *
 * @returns The TanStack Query mutation for deleting a gear.
 */
export function useDeleteGearMutation() {
  return useInvalidatingMutation<void, number>({
    mutationKey: queryKeys.gears.all(),
    excludeKeys: GEAR_WRITE_UNAFFECTED_KEYS,
    mutationFn: (id) => deleteGear(id),
  })
}
