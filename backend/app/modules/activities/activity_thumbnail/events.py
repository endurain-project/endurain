"""Domain event channel names owned by the activity-thumbnail package."""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published by the hourly tick and at every API start to ask for one pass that renders the thumbnails
# still missing. A durable subscriber runs it on an enrichment worker; without durable jobs the bus
# subscriber runs it on the in-process subscriber pool.
THUMBNAIL_BACKFILL_REQUESTED = "activity_thumbnail.backfill_requested"


class ThumbnailBackfillRequestedPayload(VersionedPayload):
    """Validated payload for the ``activity_thumbnail.backfill_requested`` event.

    The request names no activity: the pass finds the activities that are due.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1
