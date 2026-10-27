import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { useQuery } from '@tanstack/vue-query'

import type {
  GearComponent,
  GearComponentInput,
  GearComponentTypeLists,
} from '@/features/gears/types'

import { queryKeys } from '@/services/queryKeys'
import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { useAuthStore } from '@/features/auth/stores/auth'
import { GEAR_QUERY_STALE_TIME_MS } from '@/features/gears/constants'
import {
  createGearComponent,
  deleteGearComponent,
  fetchGearComponents,
  fetchGearComponentTypes,
  updateGearComponent,
} from '@/features/gears/services/gearComponents'

/**
 * The components attached to a gear, each enriched by the backend with
 * accumulated distance/time. Gated on a valid gear id and authentication.
 *
 * @param gearId - The reactive parent gear id, or `null` when none is selected.
 * @returns The TanStack Query result for the gear's components.
 */
export function useGearComponentsQuery(gearId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => toValue(gearId))

  return useQuery<GearComponent[]>({
    queryKey: computed(() => queryKeys.gears.components(id.value ?? -1)),
    queryFn: ({ signal }) => fetchGearComponents(id.value as number, signal),
    staleTime: GEAR_QUERY_STALE_TIME_MS,
    enabled: computed(
      () => isAuthenticated.value && id.value !== null && Number.isFinite(id.value),
    ),
  })
}

/**
 * The static component-type catalogues. Cached for the session (the lists never
 * change at runtime), and only fetched once a consumer needs them. Gated on
 * authentication.
 *
 * @returns The TanStack Query result for the component-type catalogues.
 */
export function useGearComponentTypesQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery<GearComponentTypeLists>({
    queryKey: queryKeys.gears.componentTypes(),
    queryFn: ({ signal }) => fetchGearComponentTypes(signal),
    staleTime: Number.POSITIVE_INFINITY,
    enabled: isAuthenticated,
  })
}

/**
 * Create mutation. Invalidates the gears domain's broad key on settle so the
 * component list, the gear detail totals, and any list view refetch the
 * server-authoritative state.
 *
 * @returns The TanStack Query mutation for creating a component.
 */
export function useCreateGearComponentMutation() {
  return useInvalidatingMutation<GearComponent, GearComponentInput>({
    mutationKey: queryKeys.gears.componentsLists(),
    mutationFn: (input) => createGearComponent(input),
    invalidateKey: queryKeys.gears.all(),
  })
}

/**
 * Update mutation. Invalidates the gears domain on settle.
 *
 * @returns The TanStack Query mutation for updating a component.
 */
export function useUpdateGearComponentMutation() {
  return useInvalidatingMutation<
    GearComponent,
    { id: number; input: GearComponentInput; version: number }
  >({
    mutationKey: queryKeys.gears.componentsLists(),
    mutationFn: ({ id, input, version }) => updateGearComponent(id, input, version),
    invalidateKey: queryKeys.gears.all(),
  })
}

/**
 * Delete mutation. Invalidates the gears domain on settle.
 *
 * @returns The TanStack Query mutation for deleting a component.
 */
export function useDeleteGearComponentMutation() {
  return useInvalidatingMutation<void, number>({
    mutationKey: queryKeys.gears.componentsLists(),
    mutationFn: (id) => deleteGearComponent(id),
    invalidateKey: queryKeys.gears.all(),
  })
}
