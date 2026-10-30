import { storeToRefs } from 'pinia'
import { useQuery } from '@tanstack/vue-query'

import type { DefaultGear } from '@/features/profile/types'
import type { Gear } from '@/features/gears/types'

import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { fetchGearsByType } from '@/features/gears/services/gears'
import { fetchDefaultGear, updateDefaultGear } from '@/features/profile/services/defaultGear'
import { DEFAULT_GEAR_TYPES } from '@/features/profile/utils/defaultGearFields'

/** Gears keyed by their numeric gear type, for the per-activity selectors. */
export type GearOptionsByType = Record<number, Gear[]>

/**
 * The user's default-gear assignments. Gated on authentication.
 *
 * @returns The TanStack Query result for the default gear (or `null`).
 */
export function useDefaultGearQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.profile.defaultGear(),
    queryFn: ({ signal }) => fetchDefaultGear(signal),
    enabled: isAuthenticated,
  })
}

/**
 * The gears the default-gear selectors can choose from, fetched per referenced
 * gear type and keyed by type. Keyed under the gears prefix so creating or
 * editing a gear refreshes the options. Gated on authentication.
 *
 * @returns The TanStack Query result for the grouped gear options.
 */
export function useGearTypeOptionsQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.gears.typeOptions(),
    queryFn: async ({ signal }): Promise<GearOptionsByType> => {
      const entries = await Promise.all(
        DEFAULT_GEAR_TYPES.map(
          async (gearType) => [gearType, await fetchGearsByType(gearType, signal)] as const,
        ),
      )
      return Object.fromEntries(entries) as GearOptionsByType
    },
    enabled: isAuthenticated,
  })
}

/**
 * Default-gear update mutation. Invalidates the default-gear cache on settle so
 * the form reflects the server-authoritative state.
 *
 * @returns The TanStack Query mutation for updating the default gear.
 */
export function useUpdateDefaultGearMutation() {
  return useInvalidatingMutation<DefaultGear, DefaultGear>({
    mutationKey: queryKeys.profile.defaultGear(),
    mutationFn: (gear) => updateDefaultGear(gear),
  })
}
