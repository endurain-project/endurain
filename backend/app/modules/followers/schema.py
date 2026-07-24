"""Pydantic schemas for follower relationships."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, StrictInt


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


class RelationshipView(BaseModel):
    """The authenticated user's relationship with another user, both directions.

    Attributes:
        outgoing: The authenticated user's follow of the other user, if any.
        incoming: The other user's follow of the authenticated user, if any.
    """

    model_config = ConfigDict(from_attributes=True)

    outgoing: FollowRelationship | None = None
    incoming: FollowRelationship | None = None


class MessageResponse(BaseModel):
    """Generic message response for follower mutation endpoints."""

    model_config = ConfigDict(from_attributes=True)

    detail: str
