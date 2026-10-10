"""Pydantic schemas for activity media."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ActivityMedia(BaseModel):
    """A photo attached to an activity, as returned to a client.

    Read-only by construction: every field is populated for a media record that
    exists, so none is optional. The stored ``StorageProvider`` key is
    deliberately absent — it is not an address, and a client has nothing to do
    with it; see :class:`~modules.activities.activity_media.contracts.ActivityMediaRecord`.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: StrictInt = Field(ge=1)
    activity_id: StrictInt = Field(ge=1)
    media_type: StrictInt = Field(ge=1, le=1)
    url: str = Field(min_length=1)
