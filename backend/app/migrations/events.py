"""Domain event channel names owned by the application's data migrations."""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published at every API start while the activity reprocess is pending, to queue one pass of it for a worker.
ACTIVITY_REPROCESS_REQUESTED = "migrations.activity_reprocess_requested"


class ActivityReprocessRequestedPayload(VersionedPayload):
    """Validated payload for the ``migrations.activity_reprocess_requested`` event.

    The request names no activity: the pass walks the activities that are due.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1
