"""Domain event channel names owned by the Garmin Connect module."""

from datetime import date
from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

import modules.garmin.constants as garmin_constants

# Published once per accepted gear or health sync when durable jobs are enabled; a durable
# subscriber runs it on a worker. Durable-delivery only: without durable jobs the sync runs on
# the module's in-process pool, so no best-effort bus subscriber exists for it.
GARMIN_SYNC_REQUESTED = "garmin.sync_requested"


class SyncRequestedPayload(VersionedPayload):
    """Validated payload for the ``garmin.sync_requested`` event.

    Attributes:
        user_id: The user whose Garmin Connect account to sync.
        kind: What to pull.
        start_date: First day of the range; set only for a health sync.
        end_date: Last day of the range; set only for a health sync.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
    kind: garmin_constants.SyncKind
    start_date: date | None = None
    end_date: date | None = None
