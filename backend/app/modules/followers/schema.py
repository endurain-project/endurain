"""Pydantic schemas for follower relationships."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator

import core.pagination as core_pagination


class FollowStatus(Enum):
    """Status of a follow relationship.

    Attributes:
        PENDING: The follow request has been sent but not yet accepted.
        ACCEPTED: The follow request has been accepted.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"


class FollowRelationship(BaseModel):
    """Serialized representation of a follow relationship."""

    model_config = ConfigDict(from_attributes=True)

    follower_id: StrictInt
    followee_id: StrictInt
    status: FollowStatus


class FollowRequestDecision(BaseModel):
    """The decision applied to a pending follow request.

    Only ``accepted`` is a valid transition: declining deletes the request rather
    than parking it in a rejected state, so a later request from the same user is
    a fresh decision instead of hitting a tombstone.
    """

    model_config = ConfigDict(from_attributes=True)

    status: FollowStatus

    @field_validator("status")
    @classmethod
    def _only_accept(cls, value: FollowStatus) -> FollowStatus:
        if value is not FollowStatus.ACCEPTED:
            raise ValueError("a follow request can only be accepted; DELETE it to decline")
        return value


class RelationshipView(BaseModel):
    """The authenticated user's relationship with another user, both directions.

    Attributes:
        outgoing: The authenticated user's follow of the other user, if any.
        incoming: The other user's follow of the authenticated user, if any.
    """

    model_config = ConfigDict(from_attributes=True)

    outgoing: FollowRelationship | None = None
    incoming: FollowRelationship | None = None


#: One page of follow relationships. Aliases the shared
#: :class:`core.pagination.Page` so the follower lists return the same envelope
#: the activities lists do — they previously returned bare, unbounded arrays,
#: which made the two template modules disagree on what a list response is.
FollowRelationshipPage = core_pagination.Page[FollowRelationship]


class MessageResponse(BaseModel):
    """Generic message response for follower mutation endpoints."""

    model_config = ConfigDict(from_attributes=True)

    detail: str
