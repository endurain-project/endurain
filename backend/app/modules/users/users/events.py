"""Domain event channel names owned by users."""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published once per accepted account deletion when durable jobs are enabled; a durable subscriber
# runs it on a worker. Durable-delivery only: without durable jobs the deletion runs on the module's
# in-process pool, so no best-effort bus subscriber exists for it.
USERS_DELETION_REQUESTED = "users.deletion_requested"


class DeletionRequestedPayload(VersionedPayload):
    """Validated payload for the ``users.deletion_requested`` event.

    Attributes:
        user_id: The user whose account and data are erased.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
