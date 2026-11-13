"""Pydantic request and response shapes for health steps records."""

import uuid
from datetime import date as datetime_date
from datetime import datetime
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, StrictInt

import core.partial_update as core_partial_update
import core.types as core_types

#: The largest value of the ``steps`` column, a 32-bit integer.
MAX_STEPS = 2_147_483_647


class Source(Enum):
    """An enumeration representing supported sources for the application.

    Members:
        MANUAL: Manually entered data
        GARMIN: Garmin health data source
    """

    MANUAL = "manual"
    GARMIN = "garmin"


class HealthStepsBase(BaseModel):
    """Base model for health steps data.

    Represents the core attributes of a user's step count record, including the user reference,
    date of the record and number of steps taken.

    Attributes:
        date (datetime_date | None): Calendar date of the steps record. Optional field.
        steps (StrictInt | None): Number of steps taken. Must be a non-negative integer. Optional field.

    Configuration:
        - from_attributes: Allows model to be populated from ORM objects.
        - extra: Forbids any extra fields not defined in the model.
        - validate_assignment: Validates field values when assigned after model creation.
        - use_enum_values: Uses enum values instead of enum objects in serialization.
    """

    date: datetime_date | None = Field(default=None, description="Calendar date of the steps")
    steps: StrictInt | None = Field(default=None, ge=0, le=MAX_STEPS, description="Number of steps taken")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthStepsWrite(HealthStepsBase):
    """Steps fields a client writes: the date is bounded, which a stored row read back need not be."""

    date: core_types.RecordDate | None = Field(default=None, description="Calendar date of the steps")


class HealthStepsCreate(HealthStepsWrite):
    """Schema for creating a health steps record.

    The date is optional; ``service`` fills it in when the client sends none.
    """

    steps: StrictInt = Field(..., ge=0, le=MAX_STEPS, description="Number of steps taken")


class HealthStepsRead(HealthStepsBase):
    """Schema for reading health steps records.

    Extends the base health steps schema with an identifier field for retrieving
    or referencing existing steps records in the database.

    Attributes:
        source (Source | None): Source of the steps data (e.g., device, API, manual entry). Optional field.
        id (uuid.UUID): Unique identifier for the steps record to update. Required field.
        user_id (uuid.UUID): Foreign key reference to the user. Required field.
    """

    source: Source = Field(default=Source.MANUAL, validate_default=True, description="Source of the steps data")
    id: uuid.UUID = Field(..., description="Unique identifier for the steps record to update")
    user_id: uuid.UUID = Field(..., description="Foreign key reference to the user")
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")
    updated_at: datetime = Field(..., description="When the record last changed, set by the server")


class HealthStepsUpdate(core_partial_update.NotClearable, HealthStepsWrite):
    """Schema for the fields a PATCH changes on a steps record.

    The record is named by the path, so the body carries neither an id nor an owner; only the
    fields present are changed.
    """

    not_clearable: ClassVar[tuple[str, ...]] = ("date", "steps")


class HealthStepsImport(HealthStepsCreate):
    """Steps record written by the server itself: a provider sync or a profile import.

    Unlike :class:`HealthStepsCreate` it carries the provenance, which a client never sets. Every
    server-side writer of ``source`` takes ``Health<Kind>Import`` (create) or ``Health<Kind>ImportUpdate``.

    Attributes:
        source (Source): The source the record came from; ``manual`` when none is given.
    """

    source: Source = Field(default=Source.MANUAL, validate_default=True, description="Source of the steps data")


class HealthStepsImportUpdate(HealthStepsUpdate):
    """Fields a provider sync or a profile import changes on a steps record, provenance included.

    Attributes:
        source (Source | None): The source the record came from.
    """

    not_clearable: ClassVar[tuple[str, ...]] = (*HealthStepsUpdate.not_clearable, "source")

    source: Source | None = Field(default=None, description="Source of the steps data")
