import type {
  FollowerDto,
  FollowList,
  FollowStatus,
  Relationship,
  RelationshipDto,
} from '@/features/followers/types'
import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'
import { fetchAllPages } from '@/services/pagination'
import { mapEmbeddedUsers, mapPublicUser } from '@/features/users/services/publicUsers'
import type { PublicUser } from '@/features/users/types'

/**
 * Page size used when loading a full follower/following list.
 *
 * The endpoints are paginated (a popular account's list would otherwise be an
 * unbounded query and response); this matches the backend's per-request cap, so
 * a single call still covers every list the UI renders today.
 */
const MAX_PAGE_SIZE = 200

/**
 * Derives the viewer's {@link FollowStatus} from a raw follow-relationship
 * record (`null` when no relationship exists).
 *
 * @param dto - The relationship record, or `null`.
 * @returns `none` (no record), `pending` (unaccepted), or `accepted`.
 */
export function mapFollowStatus(dto: FollowerDto | null): FollowStatus {
  if (!dto) {
    return 'none'
  }
  return dto.status === 'accepted' ? 'accepted' : 'pending'
}

/**
 * Maps a follow-list page to its rows and the profile of each row's user.
 *
 * @param page - The page envelope, or `null` when the body was empty.
 * @param otherUserId - Picks the other user's id (the one to display) from a row.
 * @returns The list's edges and the profiles the response carried for them.
 */
function mapFollowList(
  page: Schemas['FollowRelationshipPage'] | null,
  otherUserId: (dto: FollowerDto) => number,
): FollowList {
  const edges = (page?.items ?? []).map((dto) => ({
    userId: otherUserId(dto),
    isAccepted: dto.status === 'accepted',
  }))
  return {
    edges,
    profiles: mapEmbeddedUsers(
      edges.map((edge) => edge.userId),
      page?.users,
      mapPublicUser,
    ),
  }
}

/**
 * Fetches the people who follow a user (the user's followers list). Each row's
 * *other* user is the follower (`follower_id`).
 *
 * The endpoint is paginated and returns a page envelope; this reads the first
 * page at the maximum size, which covers every follower count the UI renders
 * today without an unbounded response.
 *
 * @param userId - The profile owner whose followers to load.
 * @param signal - Optional abort signal for cancellation.
 * @returns The follower edges (other user id + accepted flag) and each follower's profile.
 * @throws {HttpError} When the request fails.
 */
export async function fetchFollowers(userId: number, signal?: AbortSignal): Promise<FollowList> {
  const page = await apiFetch<Schemas['FollowRelationshipPage'] | null>(
    `/users/${userId}/followers?num_records=${MAX_PAGE_SIZE}`,
    { signal },
  )
  return mapFollowList(page, (dto) => dto.follower_id)
}

/**
 * Fetches the people a user follows (the user's following list). Each row's
 * *other* user is the followed user (`following_id`).
 *
 * @param userId - The profile owner whose following list to load.
 * @param signal - Optional abort signal for cancellation.
 * @returns The following edges (other user id + accepted flag) and each followed user's profile.
 * @throws {HttpError} When the request fails.
 */
export async function fetchFollowing(userId: number, signal?: AbortSignal): Promise<FollowList> {
  const page = await apiFetch<Schemas['FollowRelationshipPage'] | null>(
    `/users/${userId}/following?num_records=${MAX_PAGE_SIZE}`,
    { signal },
  )
  return mapFollowList(page, (dto) => dto.followee_id)
}

/**
 * Fetches the authenticated viewer's relationship with a target user, backing the follow
 * and block buttons. The backend's relationship endpoint reports both directions; the buttons
 * need the viewer's *outgoing* follow and whether the viewer blocked the target.
 *
 * @param targetId - The profile owner's id.
 * @param signal - Optional abort signal for cancellation.
 * @returns The viewer's {@link Relationship} with the target.
 * @throws {HttpError} When the request fails.
 */
export async function fetchRelationship(
  targetId: number,
  signal?: AbortSignal,
): Promise<Relationship> {
  const view = await apiFetch<RelationshipDto | null>(`/users/${targetId}/relationship`, {
    signal,
  })
  return { status: mapFollowStatus(view?.outgoing ?? null), isBlocked: view?.is_blocked ?? false }
}

/**
 * Sends a follow request from the authenticated viewer to the target user.
 *
 * @param targetId - The user to follow.
 * @throws {HttpError} When the request fails.
 */
export async function followUser(targetId: number): Promise<void> {
  await apiFetch<FollowerDto>(`/users/${targetId}/followers`, { method: 'POST' })
}

/**
 * Accepts a pending follow request from the target user (so they follow the
 * authenticated viewer).
 *
 * @param targetId - The requesting user to accept.
 * @throws {HttpError} When the request fails.
 */
export async function acceptFollower(targetId: number): Promise<void> {
  await apiFetch<FollowerDto>(`/profile/follow-requests/${targetId}/accept`, { method: 'POST' })
}

/**
 * Removes a user the authenticated viewer is following — i.e. unfollows the
 * target, or cancels a still-pending follow request to them.
 *
 * @param targetId - The followed (or requested) user to drop.
 * @throws {HttpError} When the request fails.
 */
export async function unfollowUser(targetId: number, viewerId: number): Promise<void> {
  // One route serves both directions; the viewer is the follower here.
  await apiFetch<void>(`/users/${targetId}/followers/${viewerId}`, {
    method: 'DELETE',
  })
}

/**
 * Removes a follower of the authenticated viewer — i.e. declines a pending
 * request, or removes an existing accepted follower.
 *
 * @param targetId - The follower to remove.
 * @throws {HttpError} When the request fails.
 */
export async function removeFollower(targetId: number, viewerId: number): Promise<void> {
  // Same route as unfollow, with the viewer as the followee instead.
  await apiFetch<void>(`/users/${viewerId}/followers/${targetId}`, {
    method: 'DELETE',
  })
}

/**
 * Fetches the users the authenticated viewer has blocked, most recently blocked first.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The public profile of each blocked user the server lists.
 * @throws {HttpError} When the request fails.
 */
export async function fetchBlockedUsers(signal?: AbortSignal): Promise<PublicUser[]> {
  const dtos = await fetchAllPages<Schemas['UserPublicRead']>('/profile/blocked-users', undefined, {
    signal,
  })
  return dtos.map(mapPublicUser)
}

/**
 * Blocks a user: they can no longer ask to follow the viewer, and any follow between the two is
 * removed. The answer is `204` for any user id.
 *
 * @param targetId - The user to block.
 * @throws {HttpError} When the request fails.
 */
export async function blockUser(targetId: number): Promise<void> {
  await apiFetch<void>(`/profile/blocked-users/${targetId}`, {
    method: 'PUT',
    responseType: 'void',
  })
}

/**
 * Unblocks a user the viewer blocked.
 *
 * @param targetId - The user to unblock.
 * @throws {HttpError} When the request fails.
 */
export async function unblockUser(targetId: number): Promise<void> {
  await apiFetch<void>(`/profile/blocked-users/${targetId}`, {
    method: 'DELETE',
    responseType: 'void',
  })
}
