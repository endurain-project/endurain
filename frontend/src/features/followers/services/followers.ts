import type {
  FollowerDto,
  FollowList,
  FollowStatus,
  Relationship,
  RelationshipDto,
} from '@/features/followers/types'
import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'
import { fetchAllPageEnvelopes, fetchAllPages } from '@/services/pagination'
import { mapEmbeddedUsers, mapPublicUser } from '@/features/users/services/publicUsers'
import type { PublicUser } from '@/features/users/types'

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

type FollowPage = Schemas['FollowRelationshipPage']

/**
 * Reads every page of a follow list and maps it to its rows and the profile of
 * each row's user.
 *
 * @param path - The list endpoint path.
 * @param otherUserId - Picks the other user's id (the one to display) from a row.
 * @param signal - Optional abort signal for cancellation.
 * @returns The list's edges and the profiles every page carried for them.
 * @throws {HttpError} When a request fails.
 */
async function fetchFollowList(
  path: string,
  otherUserId: (dto: FollowerDto) => string,
  signal?: AbortSignal,
): Promise<FollowList> {
  const pages = await fetchAllPageEnvelopes<FollowPage>(path, undefined, { signal })
  const edges = pages
    .flatMap((page) => page.items ?? [])
    .map((dto) => ({
      userId: otherUserId(dto),
      isAccepted: dto.status === 'accepted',
    }))
  const users = Object.assign({}, ...pages.map((page) => page.users))
  return {
    edges,
    profiles: mapEmbeddedUsers(
      edges.map((edge) => edge.userId),
      users,
      mapPublicUser,
    ),
  }
}

/**
 * Fetches the people who follow a user (the user's followers list). Each row's
 * *other* user is the follower (`follower_id`). Follows every page of the list.
 *
 * @param userId - The profile owner whose followers to load.
 * @param signal - Optional abort signal for cancellation.
 * @returns The follower edges (other user id + accepted flag) and each follower's profile.
 * @throws {HttpError} When the request fails.
 */
export async function fetchFollowers(userId: string, signal?: AbortSignal): Promise<FollowList> {
  return fetchFollowList(`/users/${userId}/followers`, (dto) => dto.follower_id, signal)
}

/**
 * Fetches the people a user follows (the user's following list). Each row's
 * *other* user is the followed user (`following_id`). Follows every page of the list.
 *
 * @param userId - The profile owner whose following list to load.
 * @param signal - Optional abort signal for cancellation.
 * @returns The following edges (other user id + accepted flag) and each followed user's profile.
 * @throws {HttpError} When the request fails.
 */
export async function fetchFollowing(userId: string, signal?: AbortSignal): Promise<FollowList> {
  return fetchFollowList(`/users/${userId}/following`, (dto) => dto.followee_id, signal)
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
  targetId: string,
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
export async function followUser(targetId: string): Promise<void> {
  await apiFetch<FollowerDto>(`/users/${targetId}/followers`, { method: 'POST' })
}

/**
 * Accepts a pending follow request from the target user (so they follow the
 * authenticated viewer).
 *
 * @param targetId - The requesting user to accept.
 * @throws {HttpError} When the request fails.
 */
export async function acceptFollower(targetId: string): Promise<void> {
  await apiFetch<FollowerDto>(`/profile/follow-requests/${targetId}/accept`, { method: 'POST' })
}

/**
 * Removes a user the authenticated viewer is following — i.e. unfollows the
 * target, or cancels a still-pending follow request to them.
 *
 * @param targetId - The followed (or requested) user to drop.
 * @throws {HttpError} When the request fails.
 */
export async function unfollowUser(targetId: string, viewerId: string): Promise<void> {
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
export async function removeFollower(targetId: string, viewerId: string): Promise<void> {
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
export async function blockUser(targetId: string): Promise<void> {
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
export async function unblockUser(targetId: string): Promise<void> {
  await apiFetch<void>(`/profile/blocked-users/${targetId}`, {
    method: 'DELETE',
    responseType: 'void',
  })
}
