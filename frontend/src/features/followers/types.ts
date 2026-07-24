import type { Schemas } from '@/types'

/** Raw follow-relationship payload as returned by the backend. */
export type FollowerDto = Schemas['FollowRelationship']

/** The authenticated viewer's relationship with another user, both directions. */
export type RelationshipDto = Schemas['RelationshipView']

/**
 * The viewer's follow relationship to another user, backing the follow button.
 *
 * - `none` — no relationship; the viewer can send a follow request.
 * - `pending` — the viewer has requested to follow but it is not yet accepted.
 * - `accepted` — the viewer follows the target.
 */
export type FollowStatus = 'none' | 'pending' | 'accepted'

/**
 * One row in a followers/following list: the *other* user in the relationship
 * (the follower, or the followed user) plus whether the follow is accepted.
 * Mapped from {@link FollowerDto} at the service boundary so the raw directional
 * `follower_id`/`following_id` shape never leaks into components.
 *
 * @property userId - The other user's id (the one to display and link to).
 * @property isAccepted - Whether the follow relationship has been accepted.
 */
export interface FollowEdge {
  userId: number
  isAccepted: boolean
}
