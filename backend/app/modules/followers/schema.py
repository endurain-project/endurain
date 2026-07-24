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


class MessageResponse(BaseModel):
    """Generic message response for follower mutation endpoints."""

    model_config = ConfigDict(from_attributes=True)

    detail: str
