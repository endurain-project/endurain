"""Pydantic schemas for ``GET /sync``."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

import modules.activities.activity.schema as activity_schema
import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.schema as gear_components_schema
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_targets.schema as health_targets_schema
import modules.health.health_water.schema as health_water_schema
import modules.health.health_weight.schema as health_weight_schema


class SyncType(StrEnum):
    """A kind of record ``GET /sync`` reports; the ``type`` of every change."""

    ACTIVITY = "activity"
    HEALTH_WEIGHT = "health_weight"
    HEALTH_STEPS = "health_steps"
    HEALTH_SLEEP = "health_sleep"
    HEALTH_WATER = "health_water"
    HEALTH_POOP = "health_poop"
    HEALTH_FASTING = "health_fasting"
    HEALTH_TARGETS = "health_targets"
    GEAR = "gear"
    GEAR_COMPONENT = "gear_component"


class SyncChange[RecordT: BaseModel, IdT: (int, uuid.UUID)](BaseModel):
    """One record that changed or was deleted since the cursor.

    Attributes:
        id: The record's id.
        changed_at: When it changed: its ``updated_at``, or when it was deleted.
        record: The record as its owner reads it; ``null`` when it was deleted.
    """

    model_config = ConfigDict(extra="forbid")

    id: IdT = Field(..., description="The record's id")
    changed_at: datetime = Field(..., description="When the record changed, or when it was deleted")
    record: RecordT | None = Field(default=None, description="The record; null when it was deleted")


class ActivityChange(SyncChange[activity_schema.ActivityRead, int]):
    """A changed or deleted activity."""

    type: Literal["activity"] = "activity"


class HealthWeightChange(SyncChange[health_weight_schema.HealthWeightRead, uuid.UUID]):
    """A changed or deleted weight record."""

    type: Literal["health_weight"] = "health_weight"


class HealthStepsChange(SyncChange[health_steps_schema.HealthStepsRead, uuid.UUID]):
    """A changed or deleted steps record."""

    type: Literal["health_steps"] = "health_steps"


class HealthSleepChange(SyncChange[health_sleep_schema.HealthSleepRead, uuid.UUID]):
    """A changed or deleted sleep record, with its sleep stages."""

    type: Literal["health_sleep"] = "health_sleep"


class HealthWaterChange(SyncChange[health_water_schema.HealthWaterRead, uuid.UUID]):
    """A changed or deleted water record."""

    type: Literal["health_water"] = "health_water"


class HealthPoopChange(SyncChange[health_poop_schema.HealthPoopRead, uuid.UUID]):
    """A changed or deleted bowel movement record."""

    type: Literal["health_poop"] = "health_poop"


class HealthFastingChange(SyncChange[health_fasting_schema.HealthFastingRead, uuid.UUID]):
    """A changed or deleted fasting record."""

    type: Literal["health_fasting"] = "health_fasting"


class HealthTargetsChange(SyncChange[health_targets_schema.HealthTargetsRead, uuid.UUID]):
    """A changed or deleted set of health targets."""

    type: Literal["health_targets"] = "health_targets"


class GearChange(SyncChange[gear_schema.GearDetailRead, int]):
    """A changed or deleted gear, with its totals; the totals follow activities without stamping the gear."""

    type: Literal["gear"] = "gear"


class GearComponentChange(SyncChange[gear_components_schema.GearComponentRead, int]):
    """A changed or deleted gear component."""

    type: Literal["gear_component"] = "gear_component"


#: A change of any record type, told apart by ``type``.
Change = Annotated[
    ActivityChange
    | HealthWeightChange
    | HealthStepsChange
    | HealthSleepChange
    | HealthWaterChange
    | HealthPoopChange
    | HealthFastingChange
    | HealthTargetsChange
    | GearChange
    | GearComponentChange,
    Field(discriminator="type"),
]


class SyncPage(BaseModel):
    """A slice of the changes since a cursor, oldest first.

    Attributes:
        changes: The changes and deletions, in the order they happened.
        next_cursor: Where the next request continues; keep it after the last page too, for the next sync.
        has_more: Whether more changes are already waiting; ask again at once while it is true.
    """

    model_config = ConfigDict(extra="forbid")

    changes: list[Change] = Field(..., description="The changes and deletions, oldest first")
    next_cursor: str = Field(..., description="Where the next sync continues; keep it after the last page too")
    has_more: bool = Field(..., description="Whether more changes are waiting; ask again at once while true")
