import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { useQuery } from '@tanstack/vue-query'

import type { PublicUser, UserProfileOverview } from '@/features/users/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { fetchPublicUser, searchPublicUsers } from '@/features/users/services/publicUsers'
import { fetchUserProfileOverview } from '@/features/users/services/profileOverview'
import { todayIsoDate } from '@/utils/datetime'

/** Resolves a reactive user id to a positive number, or `0` when unavailable. */
function resolveUserId(userId: MaybeRefOrGetter<number | null>): number {
  const value = toValue(userId)
  return value !== null && Number.isFinite(value) && value > 0 ? value : 0
}

/**
 * A user's public-facing profile, backing the `/user/:id` page header and every
 * follower/following list row (deduplicated by id through the shared cache key).
 * Gated on a valid user id and authentication.
 *
 * @param userId - Reactive id of the user to load.
 * @returns The TanStack query result for the public user (`null` when missing).
 */
export function usePublicUserQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery<PublicUser | null>({
    queryKey: computed(() => queryKeys.users.publicProfile(id.value)),
    queryFn: ({ signal }) => fetchPublicUser(id.value, signal),
    enabled: computed(() => isAuthenticated.value && id.value > 0),
    staleTime: 5 * 60_000,
  })
}

/**
 * The public profile and its week/month summary values, loaded in one request.
 * The activity-domain key lets activity writes invalidate this aggregate.
 *
 * @param userId - Reactive id of the profile owner.
 * @returns The TanStack query result for the profile overview.
 */
export function useUserProfileOverviewQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery<UserProfileOverview>({
    queryKey: computed(() => queryKeys.activities.profileOverview(id.value)),
    queryFn: ({ signal }) => fetchUserProfileOverview(id.value, todayIsoDate(), signal),
    enabled: computed(() => isAuthenticated.value && id.value > 0),
    staleTime: 5 * 60_000,
  })
}

/**
 * Username "contains" search over active users. Enabled only once the
 * (debounced) term is non-empty so an empty box never fires a request; gated on
 * authentication.
 *
 * @param term - The reactive (debounced) search term.
 * @returns The TanStack Query result for the matching users.
 */
export function useUserSearchQuery(term: MaybeRefOrGetter<string>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const trimmed = computed(() => toValue(term).trim())

  return useQuery<PublicUser[]>({
    queryKey: computed(() => queryKeys.users.search(trimmed.value)),
    queryFn: ({ signal }) => searchPublicUsers(trimmed.value, signal),
    enabled: computed(() => isAuthenticated.value && trimmed.value.length > 0),
  })
}
