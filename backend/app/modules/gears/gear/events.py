"""Domain event channels owned by the gear package."""

import uuid
from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

#: Published when a gear deletion is accepted, so a durable worker unassigns the gear from the activities that
#: carry it and deletes it.
GEAR_DELETION_REQUESTED = "gears.deletion_requested"


class DeletionRequestedPayload(VersionedPayload):
    """Validated payload for the ``gears.deletion_requested`` event.

    Attributes:
        user_id: The gear's owner.
        gear_id: The gear to delete.
        job_id: The job the deletion records its state against.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: uuid.UUID
    gear_id: uuid.UUID
    job_id: uuid.UUID
