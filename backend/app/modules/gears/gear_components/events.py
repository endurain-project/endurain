"""Domain event channels owned by the gear components package.

Convention: ``<domain>.<fact>``, past tense. Bump a payload's ``SCHEMA_VERSION`` (and
register an upgrader for the step) whenever a field is renamed, removed, or given a new
meaning; a purely additive optional field does not need one. See
:mod:`jasil.event_versioning`.
"""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict, Field

# Published after a gear component is created.
GEAR_COMPONENT_CREATED = "gear_component.created"

# Published after a gear component's own columns change.
GEAR_COMPONENT_UPDATED = "gear_component.updated"

# Published after a gear component is deleted on its own. Components removed with their
# gear are covered by ``gear.deleted``.
GEAR_COMPONENT_DELETED = "gear_component.deleted"


class GearComponentCreatedPayload(VersionedPayload):
    """Validated payload for the ``gear_component.created`` event.

    Attributes:
        gear_component_id: The created component's ID.
        gear_id: The gear it belongs to.
        user_id: The owning user's ID.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    gear_component_id: int
    gear_id: int
    user_id: int


class GearComponentUpdatedPayload(VersionedPayload):
    """Validated payload for the ``gear_component.updated`` event.

    Attributes:
        gear_component_id: The updated component's ID.
        gear_id: The gear it belongs to.
        user_id: The owning user's ID.
        changed_fields: Names of the component columns this update wrote, sorted.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    gear_component_id: int
    gear_id: int
    user_id: int
    changed_fields: list[str] = Field(default_factory=list)


class GearComponentDeletedPayload(VersionedPayload):
    """Validated payload for the ``gear_component.deleted`` event.

    Attributes:
        gear_component_id: The removed component's ID.
        gear_id: The gear it belonged to.
        user_id: The owning user's ID.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    gear_component_id: int
    gear_id: int
    user_id: int
