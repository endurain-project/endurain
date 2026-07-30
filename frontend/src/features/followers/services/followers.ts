import type {
  FollowEdge,
  FollowerDto,
  FollowStatus,
  RelationshipDto,
} from '@/features/followers/types'
import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'

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
 * Fetches the people who follow a user (the user's followers list). Each row's
 * *other* user is the follower (`follower_id`).
 *
 * @param userId - The profile owner whose followers to load.
 * @param signal - Optional abort signal for cancellation.
 * @returns The follower edges (other user id + accepted flag).
 * @throws {HttpError} When the request fails.
 */
export async function fetchFollowers(userId: number, signal?: AbortSignal): Promise<FollowEdge[]> {
  const dtos = await apiFetch<FollowerDto[] | null>(`/followers/users/${userId}/followers`, {
    signal,
  })
  return (dtos ?? []).map((dto) => ({
    userId: dto.follower_id,
    isAccepted: dto.status === 'accepted',
  }))
}

/**
 * Fetches the people a user follows (the user's following list). Each row's
 * *other* user is the followed user (`following_id`).
 *
 * @param userId - The profile owner whose following list to load.
 * @param signal - Optional abort signal for cancellation.
 * @returns The following edges (other user id + accepted flag).
 * @throws {HttpError} When the request fails.
 */
export async function fetchFollowing(userId: number, signal?: AbortSignal): Promise<FollowEdge[]> {
  const dtos = await apiFetch<FollowerDto[] | null>(`/followers/users/${userId}/following`, {
    signal,
  })
  return (dtos ?? []).map((dto) => ({
    userId: dto.followee_id,
    isAccepted: dto.status === 'accepted',
  }))
}

/**
 * Fetches a user's accepted-followers count (public-profile header).
 *
 * @param userId - The profile owner whose follower count to load.
 * @param signal - Optional abort signal for cancellation.
 * @returns The number of accepted followers.
 * @throws {HttpError} When the request fails.
 */
export async function fetchFollowersCount(userId: number, signal?: AbortSignal): Promise<number> {
  return apiFetch<number>(`/followers/users/${userId}/followers/count?accepted_only=true`, {
    signal,
  })
}

/**
 * Fetches a user's accepted-following count (public-profile header).
 *
 * @param userId - The profile owner whose following count to load.
 * @param signal - Optional abort signal for cancellation.
 * @returns The number of users the profile owner follows (accepted).
 * @throws {HttpError} When the request fails.
 */
export async function fetchFollowingCount(userId: number, signal?: AbortSignal): Promise<number> {
  return apiFetch<number>(`/followers/users/${userId}/following/count?accepted_only=true`, {
    signal,
  })
}

/**
 * Fetches the authenticated viewer's follow relationship to a target user,
 * backing the follow button's state. The backend's relationship endpoint reports
 * both directions; the button only needs the viewer's *outgoing* follow.
 *
 * @param targetId - The profile owner's id.
 * @param signal - Optional abort signal for cancellation.
 * @returns The viewer's {@link FollowStatus} for the target.
 * @throws {HttpError} When the request fails.
 */
export async function fetchFollowStatus(
  targetId: number,
  signal?: AbortSignal,
): Promise<FollowStatus> {
  const view = await apiFetch<RelationshipDto | null>(`/followers/users/${targetId}/relationship`, {
    signal,
  })
  return mapFollowStatus(view?.outgoing ?? null)
}

/**
 * Sends a follow request from the authenticated viewer to the target user.
 *
 * @param targetId - The user to follow.
 * @throws {HttpError} When the request fails.
 */
export async function followUser(targetId: number): Promise<void> {
  await apiFetch<FollowerDto>(`/followers/users/${targetId}/follow`, { method: 'POST' })
}

/**
 * Accepts a pending follow request from the target user (so they follow the
 * authenticated viewer).
 *
 * @param targetId - The requesting user to accept.
 * @throws {HttpError} When the request fails.
 */
export async function acceptFollower(targetId: number): Promise<void> {
  await apiFetch<Schemas['MessageResponse']>(`/followers/users/${targetId}/follow/accept`, {
    method: 'POST',
  })
}

/**
 * Removes a user the authenticated viewer is following — i.e. unfollows the
 * target, or cancels a still-pending follow request to them.
 *
 * @param targetId - The followed (or requested) user to drop.
 * @throws {HttpError} When the request fails.
 */
export async function unfollowUser(targetId: number): Promise<void> {
  await apiFetch<Schemas['MessageResponse']>(`/followers/users/${targetId}/follow`, {
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
export async function removeFollower(targetId: number): Promise<void> {
  await apiFetch<Schemas['MessageResponse']>(`/followers/users/${targetId}/follower`, {
    method: 'DELETE',
  })
}
