"""Pydantic schemas for activity media."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ActivityMedia(BaseModel):
    """Activity media payload (photo/video attached to an activity)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: StrictInt | None = None
    activity_id: StrictInt = Field(ge=1)
    media_path: str = Field(min_length=1, max_length=250)
    media_type: StrictInt = Field(ge=1, le=1)
