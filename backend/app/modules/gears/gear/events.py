"""Domain event channels owned by the gear package.

Convention: ``<domain>.<fact>``, past tense. Bump a payload's ``SCHEMA_VERSION`` (and
register an upgrader for the step) whenever a field is renamed, removed, or given a new
meaning; a purely additive optional field does not need one. See
:mod:`jasil.event_versioning`.
"""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict, Field

# Published after a gear is created through the API.
GEAR_CREATED = "gear.created"

# Published after a gear's own columns change.
GEAR_UPDATED = "gear.updated"

# Published after a gear is deleted, once the activities that carried it have been
# unassigned.
GEAR_DELETED = "gear.deleted"


class GearCreatedPayload(VersionedPayload):
    """Validated payload for the ``gear.created`` event.

    Attributes:
        gear_id: The created gear's ID.
        user_id: The owning user's ID.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    gear_id: int
    user_id: int


class GearUpdatedPayload(VersionedPayload):
    """Validated payload for the ``gear.updated`` event.

    Attributes:
        gear_id: The updated gear's ID.
        user_id: The owning user's ID.
        changed_fields: Names of the gear columns this update wrote, sorted.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    gear_id: int
    user_id: int
    changed_fields: list[str] = Field(default_factory=list)


class GearDeletedPayload(VersionedPayload):
    """Validated payload for the ``gear.deleted`` event.

    Attributes:
        gear_id: The removed gear's ID.
        user_id: The owning user's ID.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    gear_id: int
    user_id: int
