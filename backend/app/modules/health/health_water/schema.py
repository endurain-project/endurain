"""Pydantic schemas for health water intake data.

This module defines the request/response schemas for water intake
tracking, including validation rules and source enumeration.
"""

import uuid
from datetime import date as datetime_date
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
)

import core.partial_update as core_partial_update
import core.types as core_types

#: The most water, in milliliters, one day can total.
MAX_WATER_ML = 20000


class Source(StrEnum):
    """Enumeration of data sources for water intake records.

    Attributes:
        MANUAL: Manually entered water intake data.
        GARMIN: Garmin fitness tracking platform as a data source.
    """

    MANUAL = "manual"
    GARMIN = "garmin"


class HealthWaterBase(BaseModel):
    """Base model for health water intake data.

    Attributes:
        date: Calendar date of the water intake record.
        amount_ml: Water consumed in milliliters.
    """

    date: datetime_date | None = Field(
        default=None,
        description="Calendar date of the water intake",
    )
    amount_ml: StrictFloat | None = Field(
        default=None,
        ge=0,
        le=MAX_WATER_ML,
        description="Water consumed in milliliters",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthWaterWrite(HealthWaterBase):
    """Water fields a client writes: the date is bounded, which a stored row read back need not be."""

    date: core_types.RecordDate | None = Field(default=None, description="Calendar date of the water intake")


class HealthWaterCreate(HealthWaterWrite):
    """Schema for creating a new water intake record.

    The date is optional; ``service`` fills it in when the client sends none.
    """

    amount_ml: StrictFloat = Field(..., ge=0, le=MAX_WATER_ML, description="Water consumed in milliliters")


class HealthWaterRead(HealthWaterBase):
    """Schema for reading a water intake record.

    Attributes:
        source: Source of the water intake data.
        id: Unique identifier for the water intake record.
        user_id: Foreign key reference to the user.
    """

    source: Source = Field(
        default=Source.MANUAL,
        validate_default=True,
        description="Source of the water intake data",
    )
    id: uuid.UUID = Field(
        ...,
        description=("Unique identifier for the water intake record"),
    )
    user_id: StrictInt = Field(
        ...,
        description="Foreign key reference to the user",
    )
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")
    updated_at: datetime = Field(..., description="When the record last changed, set by the server")


class HealthWaterUpdate(core_partial_update.NotClearable, HealthWaterWrite):
    """Schema for the fields a PATCH changes on a water record.

    The record is named by the path, so the body carries neither an id nor an owner; only the
    fields present are changed.
    """

    not_clearable: ClassVar[tuple[str, ...]] = ("date", "amount_ml")


class HealthWaterImport(HealthWaterCreate):
    """Water record written by the server itself: a profile import.

    Unlike :class:`HealthWaterCreate` it carries the provenance, which a client never sets. Every
    server-side writer of ``source`` takes ``Health<Kind>Import`` (create) or ``Health<Kind>ImportUpdate``.

    Attributes:
        source: The source the record came from; ``manual`` when none is given.
    """

    source: Source = Field(default=Source.MANUAL, validate_default=True, description="Source of the water intake data")


class HealthWaterImportUpdate(HealthWaterUpdate):
    """Fields a profile import changes on a water record, provenance included.

    Attributes:
        source: The source the record came from.
    """

    not_clearable: ClassVar[tuple[str, ...]] = (*HealthWaterUpdate.not_clearable, "source")

    source: Source | None = Field(default=None, description="Source of the water intake data")
