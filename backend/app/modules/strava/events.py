"""Domain event channel names owned by the Strava module."""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

import modules.strava.constants as strava_constants

# Published once per accepted gear sync or unlink when durable jobs are enabled; a durable
# subscriber runs it on a worker. Durable-delivery only: without durable jobs the sync runs on
# the module's in-process pool, so no best-effort bus subscriber exists for it.
STRAVA_SYNC_REQUESTED = "strava.sync_requested"


class SyncRequestedPayload(VersionedPayload):
    """Validated payload for the ``strava.sync_requested`` event.

    Attributes:
        user_id: The user whose Strava account to sync.
        kind: What to do.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
    kind: strava_constants.SyncKind
