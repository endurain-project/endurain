"""Internal activity-media contract: the persisted record.

Separate from ``schema.py`` (the API read model) for the reason
:mod:`modules.activities.activity.contracts` states: this is an **inter-module
interface**, not an HTTP shape. It carries the ``StorageProvider`` key, which the
persistence layer, the deletion cleanup, and the profile export/import all need,
and which a client has no use for — it is not an address and cannot be fetched.

Keeping the two apart is what lets the read model declare ``id`` and ``url`` as
required. While one class served as read response, CRUD return type, export DTO
*and* import input, both had to be nullable to satisfy the write paths, so every
reader had to null-check fields that are in fact always present on a read.
"""

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ActivityMediaRecord(BaseModel):
    """A stored activity media row, as persisted and as archived.

    Attributes:
        id: Row id; ``None`` before the row is created.
        activity_id: The activity the media belongs to.
        media_path: The ``StorageProvider`` key the blob is stored under
            (``{activity_id}_{uuid}{ext}``). Not a filesystem path and not
            servable; :func:`modules.activities.activity_media.signing.media_url`
            turns it into an address.
        media_type: Media kind (1 = photo).
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: StrictInt | None = None
    activity_id: StrictInt = Field(ge=1)
    media_path: str = Field(min_length=1, max_length=250)
    media_type: StrictInt = Field(ge=1, le=1)
