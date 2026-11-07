"""Pydantic schemas for follower relationships."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt

import core.pagination as core_pagination
import modules.followers.constants as followers_constants
import modules.users.users.schema as users_schema


class FollowRelationshipRead(BaseModel):
    """Serialized representation of a follow relationship.

    Attributes:
        follower_id: The user who follows (the requester).
        followee_id: The user being followed.
        status: Whether the request is pending or accepted.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    follower_id: StrictInt
    followee_id: StrictInt
    status: followers_constants.FollowStatus


class RelationshipRead(BaseModel):
    """The authenticated user's relationship with another user, both directions.

    Attributes:
        outgoing: The authenticated user's follow of the other user, if any.
        incoming: The other user's follow of the authenticated user, if any.
        is_blocked: Whether the authenticated user has blocked the other user.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    outgoing: FollowRelationshipRead | None = None
    incoming: FollowRelationshipRead | None = None
    is_blocked: bool = False


class FollowRelationshipPage(core_pagination.Page[FollowRelationshipRead]):
    """One page of follow relationships, in the envelope the activities lists use.

    Attributes:
        users: The public profile of the user on the other side of each row (the follower in a
            followers list, the followee in a following list, the requester among pending requests),
            keyed by user ID. It is the projection ``GET /users/{user_id}`` returns, so a list needs
            no lookup per row. A user who is inactive or awaiting approval has no entry.
    """

    users: dict[int, users_schema.UserPublicRead] = Field(
        default_factory=dict,
        description="Public profile of the user on the other side of each row, keyed by user ID",
    )
