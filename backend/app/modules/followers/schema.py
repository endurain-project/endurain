"""Pydantic schemas for follower relationships."""

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt


class Follower(BaseModel):
    """Serialized representation of a follower relationship."""

    model_config = ConfigDict(from_attributes=True)

    follower_id: StrictInt
    following_id: StrictInt
    is_accepted: StrictBool


class MessageResponse(BaseModel):
    """Generic message response for follower mutation endpoints."""

    model_config = ConfigDict(from_attributes=True)

    detail: str
