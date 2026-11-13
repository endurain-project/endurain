import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { FollowEdge, FollowStatus, Relationship } from '@/features/followers/types'
import type { PublicUser } from '@/features/users/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import {
  acceptFollower,
  blockUser,
  fetchBlockedUsers,
  fetchFollowers,
  fetchFollowing,
  fetchRelationship,
  followUser,
  removeFollower,
  unblockUser,
  unfollowUser,
} from '@/features/followers/services/followers'

/** Freshness window for follow graph reads; relationship writes invalidate the domain. */
const FOLLOWER_QUERY_STALE_TIME_MS = 60_000

/** Resolves a reactive user id to its string, or `''` when unavailable. */
function resolveUserId(userId: MaybeRefOrGetter<string | null>): string {
  return toValue(userId) ?? ''
}

/**
 * Writes the profiles a follow list carried into the public-profile cache its rows read, so
 * a row finds its user there instead of requesting it.
 *
 * @param client - The active query client.
 * @param profiles - Each row's profile, or `null` for a user the server left out.
 */
function seedPublicProfiles(
  client: QueryClient,
  profiles: ReadonlyMap<string, PublicUser | null>,
): void {
  for (const [userId, profile] of profiles) {
    client.setQueryData(queryKeys.users.publicProfile(userId), profile)
  }
}

/**
 * The people who follow a user (the profile's followers list). Gated on a valid
 * user id and authentication. The followers' profiles arrive with the list and are
 * seeded into the public-profile cache.
 *
 * @param userId - Reactive id of the profile owner.
 * @param enabled - Reactive gate for whether the list is currently needed.
 * @returns The TanStack query result for the followers list.
 */
export function useFollowersQuery(
  userId: MaybeRefOrGetter<string | null>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const client = useQueryClient()
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery<FollowEdge[]>({
    queryKey: computed(() => queryKeys.followers.followersList(id.value)),
    queryFn: async ({ signal }) => {
      const { edges, profiles } = await fetchFollowers(id.value, signal)
      seedPublicProfiles(client, profiles)
      return edges
    },
    staleTime: FOLLOWER_QUERY_STALE_TIME_MS,
    enabled: computed(() => toValue(enabled) && isAuthenticated.value && id.value !== ''),
  })
}

/**
 * The people a user follows (the profile's following list). Gated on a valid
 * user id and authentication. The followed users' profiles arrive with the list and
 * are seeded into the public-profile cache.
 *
 * @param userId - Reactive id of the profile owner.
 * @param enabled - Reactive gate for whether the list is currently needed.
 * @returns The TanStack query result for the following list.
 */
export function useFollowingQuery(
  userId: MaybeRefOrGetter<string | null>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const client = useQueryClient()
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery<FollowEdge[]>({
    queryKey: computed(() => queryKeys.followers.followingList(id.value)),
    queryFn: async ({ signal }) => {
      const { edges, profiles } = await fetchFollowing(id.value, signal)
      seedPublicProfiles(client, profiles)
      return edges
    },
    staleTime: FOLLOWER_QUERY_STALE_TIME_MS,
    enabled: computed(() => toValue(enabled) && isAuthenticated.value && id.value !== ''),
  })
}

/**
 * The authenticated viewer's relationship with a target user, backing the follow and block
 * buttons. Gated on authentication and a valid target that is not the viewer themselves (no
 * self-follow state). Both buttons read the same cached response.
 *
 * @param targetId - Reactive id of the profile owner being viewed.
 * @param select - Picks what the caller needs from the {@link Relationship}.
 * @returns The TanStack query result for the selected part of the relationship.
 */
function useRelationshipQuery<T>(
  targetId: MaybeRefOrGetter<string | null>,
  select: (relationship: Relationship) => T,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const { data: currentUser } = useCurrentUser()
  const viewerId = computed(() => currentUser.value?.id ?? null)
  const target = computed(() => resolveUserId(targetId))

  return useQuery<Relationship, Error, T>({
    queryKey: computed(() => queryKeys.followers.state(viewerId.value ?? '', target.value)),
    queryFn: ({ signal }) => fetchRelationship(target.value, signal),
    select,
    staleTime: FOLLOWER_QUERY_STALE_TIME_MS,
    enabled: computed(
      () =>
        isAuthenticated.value &&
        viewerId.value !== null &&
        target.value !== '' &&
        viewerId.value !== target.value,
    ),
  })
}

/**
 * The authenticated viewer's follow status towards a target user, backing the follow button.
 *
 * @param targetId - Reactive id of the profile owner being viewed.
 * @returns The TanStack query result for the viewer's {@link FollowStatus}.
 */
export function useFollowStatusQuery(targetId: MaybeRefOrGetter<string | null>) {
  return useRelationshipQuery<FollowStatus>(targetId, (relationship) => relationship.status)
}

/**
 * Whether the authenticated viewer has blocked a target user, backing the block button.
 *
 * @param targetId - Reactive id of the profile owner being viewed.
 * @returns The TanStack query result for the block state.
 */
export function useIsBlockedQuery(targetId: MaybeRefOrGetter<string | null>) {
  return useRelationshipQuery<boolean>(targetId, (relationship) => relationship.isBlocked)
}

/**
 * The users the authenticated viewer has blocked.
 *
 * @returns The TanStack query result for the block list.
 */
export function useBlockedUsersQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery<PublicUser[]>({
    queryKey: queryKeys.followers.blocked(),
    queryFn: ({ signal }) => fetchBlockedUsers(signal),
    staleTime: FOLLOWER_QUERY_STALE_TIME_MS,
    enabled: isAuthenticated,
  })
}

/**
 * Builds a follow-graph mutation that invalidates the whole `followers` domain
 * on settle, so every affected list, count, and relationship-state query
 * refetches the server-authoritative state.
 *
 * @param mutationFn - The service call the mutation performs (keyed by target id).
 * @returns A configured TanStack mutation taking the target user id.
 */
function useFollowGraphMutation(mutationFn: (targetId: string) => Promise<void>) {
  const client = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn,
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.followers.all() })
      void client.invalidateQueries({ queryKey: queryKeys.activities.profileOverviews() })
    },
  })
}

/**
 * Builds a follow-graph mutation for the relationship-delete route, which takes
 * both parties: one endpoint now serves unfollow and remove-follower, told apart
 * by which side the viewer is on.
 *
 * @param mutationFn - The service call, taking the target and the viewer id.
 * @returns A configured TanStack mutation taking the target user id.
 */
function useRelationshipDeleteMutation(
  mutationFn: (targetId: string, viewerId: string) => Promise<void>,
) {
  const client = useQueryClient()
  const { data: currentUser } = useCurrentUser()

  return useMutation<void, Error, string>({
    mutationFn: (targetId: string) => {
      const viewerId = currentUser.value?.id
      if (viewerId === undefined) {
        return Promise.reject(new Error('No authenticated user'))
      }
      return mutationFn(targetId, viewerId)
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.followers.all() })
      void client.invalidateQueries({ queryKey: queryKeys.activities.profileOverviews() })
    },
  })
}

/**
 * Sends a follow request from the authenticated viewer to the target user.
 *
 * @returns The TanStack mutation taking the target user id.
 */
export function useFollowUserMutation() {
  return useFollowGraphMutation(followUser)
}

/**
 * Accepts a pending follow request from the target user.
 *
 * @returns The TanStack mutation taking the requesting user id.
 */
export function useAcceptFollowerMutation() {
  return useFollowGraphMutation(acceptFollower)
}

/**
 * Unfollows the target user, or cancels a still-pending request to them.
 *
 * @returns The TanStack mutation taking the followed (or requested) user id.
 */
export function useUnfollowUserMutation() {
  return useRelationshipDeleteMutation(unfollowUser)
}

/**
 * Removes a follower of the authenticated viewer — declines a pending request
 * or removes an accepted follower.
 *
 * @returns The TanStack mutation taking the follower's user id.
 */
export function useRemoveFollowerMutation() {
  return useRelationshipDeleteMutation(removeFollower)
}

/**
 * Blocks a user, which also removes any follow between the viewer and them.
 *
 * @returns The TanStack mutation taking the user id to block.
 */
export function useBlockUserMutation() {
  return useFollowGraphMutation(blockUser)
}

/**
 * Unblocks a user the viewer blocked.
 *
 * @returns The TanStack mutation taking the user id to unblock.
 */
export function useUnblockUserMutation() {
  return useFollowGraphMutation(unblockUser)
}
