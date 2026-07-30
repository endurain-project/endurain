import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { FollowEdge, FollowStatus } from '@/features/followers/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import {
  acceptFollower,
  fetchFollowers,
  fetchFollowersCount,
  fetchFollowing,
  fetchFollowingCount,
  fetchFollowStatus,
  followUser,
  removeFollower,
  unfollowUser,
} from '@/features/followers/services/followers'

/** Resolves a reactive user id to a positive number, or `0` when unavailable. */
function resolveUserId(userId: MaybeRefOrGetter<number | null>): number {
  const value = toValue(userId)
  return value !== null && Number.isFinite(value) && value > 0 ? value : 0
}

/**
 * The people who follow a user (the profile's followers list). Gated on a valid
 * user id and authentication.
 *
 * @param userId - Reactive id of the profile owner.
 * @returns The TanStack query result for the followers list.
 */
export function useFollowersQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery<FollowEdge[]>({
    queryKey: computed(() => queryKeys.followers.followersList(id.value)),
    queryFn: ({ signal }) => fetchFollowers(id.value, signal),
    enabled: computed(() => isAuthenticated.value && id.value > 0),
  })
}

/**
 * The people a user follows (the profile's following list). Gated on a valid
 * user id and authentication.
 *
 * @param userId - Reactive id of the profile owner.
 * @returns The TanStack query result for the following list.
 */
export function useFollowingQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery<FollowEdge[]>({
    queryKey: computed(() => queryKeys.followers.followingList(id.value)),
    queryFn: ({ signal }) => fetchFollowing(id.value, signal),
    enabled: computed(() => isAuthenticated.value && id.value > 0),
  })
}

/**
 * A user's accepted-followers count (public-profile header). Gated on a valid
 * user id and authentication.
 *
 * @param userId - Reactive id of the profile owner.
 * @returns The TanStack query result for the followers count.
 */
export function useFollowersCountQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery<number>({
    queryKey: computed(() => queryKeys.followers.followersCount(id.value)),
    queryFn: ({ signal }) => fetchFollowersCount(id.value, signal),
    enabled: computed(() => isAuthenticated.value && id.value > 0),
  })
}

/**
 * A user's accepted-following count (public-profile header). Gated on a valid
 * user id and authentication.
 *
 * @param userId - Reactive id of the profile owner.
 * @returns The TanStack query result for the following count.
 */
export function useFollowingCountQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery<number>({
    queryKey: computed(() => queryKeys.followers.followingCount(id.value)),
    queryFn: ({ signal }) => fetchFollowingCount(id.value, signal),
    enabled: computed(() => isAuthenticated.value && id.value > 0),
  })
}

/**
 * The authenticated viewer's follow relationship to a target user, backing the
 * follow button. Gated on authentication and a valid target that is not the
 * viewer themselves (no self-follow state).
 *
 * @param targetId - Reactive id of the profile owner being viewed.
 * @returns The TanStack query result for the viewer's {@link FollowStatus}.
 */
export function useFollowStatusQuery(targetId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const { data: currentUser } = useCurrentUser()
  const viewerId = computed(() => currentUser.value?.id ?? 0)
  const target = computed(() => resolveUserId(targetId))

  return useQuery<FollowStatus>({
    queryKey: computed(() => queryKeys.followers.state(viewerId.value, target.value)),
    queryFn: ({ signal }) => fetchFollowStatus(target.value, signal),
    enabled: computed(
      () =>
        isAuthenticated.value &&
        viewerId.value > 0 &&
        target.value > 0 &&
        viewerId.value !== target.value,
    ),
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
function useFollowGraphMutation(mutationFn: (targetId: number) => Promise<void>) {
  const client = useQueryClient()

  return useMutation<void, Error, number>({
    mutationFn,
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.followers.all() })
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
  mutationFn: (targetId: number, viewerId: number) => Promise<void>,
) {
  const client = useQueryClient()
  const { data: currentUser } = useCurrentUser()

  return useMutation<void, Error, number>({
    mutationFn: (targetId: number) => mutationFn(targetId, currentUser.value?.id ?? 0),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.followers.all() })
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
