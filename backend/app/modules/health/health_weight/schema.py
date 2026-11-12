"""Pydantic request and response shapes for health weight records."""

import uuid
from datetime import date as datetime_date
from datetime import datetime
from enum import Enum
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

MAX_BMI = 100
"""Highest BMI a record may carry; a calculated value above it is unusable and not stored."""


class Source(Enum):
    """Enumeration of data sources for health weight records.

    Attributes:
        MANUAL: Manually entered data.
        GARMIN: Garmin fitness tracking platform as a data source.
    """

    MANUAL = "manual"
    GARMIN = "garmin"


class HealthWeightBase(BaseModel):
    """Pydantic model for health weight data.

    This model defines the structure and validation rules for health weight information,
    including body composition metrics and related health indicators.

    Attributes:
        date (datetime_date | None): The date of the health weight measurement.
        weight_kg (StrictFloat | None): Weight in kilograms. Must be between 0 and 500.
        bmi (StrictFloat | None): Body Mass Index value. Must be between 0 and 100.
        body_fat_percent (StrictFloat | None): Body fat percentage. Must be between 0 and 100.
        body_water_percent (StrictFloat | None): Body water percentage. Must be between 0 and 100.
        bone_mass_kg (StrictFloat | None): Bone mass in kilograms. Must be between 0 and 500.
        muscle_mass_kg (StrictFloat | None): Muscle mass in kilograms. Must be between 0 and 500.
        physique_rating (StrictInt | None): Physique rating score. Must be greater than or equal to 0.
        visceral_fat (StrictFloat | None): Visceral fat percentage. Must be between 0 and 100.
        metabolic_age (StrictInt | None): Metabolic age in years. Must be between 0 and 120.

    Model Configuration:
        - Populates from ORM attributes
        - Forbids extra fields
        - Validates assignments
        - Uses enum values for serialization
    """

    date: datetime_date | None = Field(default=None, description="Health weight date (date)")
    weight_kg: StrictFloat | None = Field(default=None, ge=0, le=500, description="Weight in kilograms")
    bmi: StrictFloat | None = Field(
        default=None,
        ge=0,
        le=MAX_BMI,
        description="Body Mass Index; a manually entered record ignores a value sent and derives it from the weight and height",
    )
    body_fat_percent: StrictFloat | None = Field(
        default=None, ge=0, le=100, description="Body fat as a percentage of body weight (0-100)"
    )
    body_water_percent: StrictFloat | None = Field(
        default=None, ge=0, le=100, description="Body water as a percentage of body weight (0-100)"
    )
    bone_mass_kg: StrictFloat | None = Field(default=None, ge=0, le=500, description="Bone mass in kilograms")
    muscle_mass_kg: StrictFloat | None = Field(default=None, ge=0, le=500, description="Muscle mass in kilograms")
    physique_rating: StrictInt | None = Field(default=None, ge=0, description="Physique rating, a score (not a unit)")
    visceral_fat: StrictFloat | None = Field(
        default=None, ge=0, le=100, description="Visceral fat rating (a score, not a unit)"
    )
    metabolic_age: StrictInt | None = Field(default=None, ge=0, le=120, description="Metabolic age in years")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthWeightWrite(HealthWeightBase):
    """Weight fields a client writes: the date is bounded, which a stored row read back need not be."""

    date: core_types.RecordDate | None = Field(default=None, description="Health weight date (date)")


class HealthWeightCreate(HealthWeightWrite):
    """Schema for creating a health weight record.

    The date is optional; ``service`` fills it in when the client sends none.
    """

    weight_kg: StrictFloat = Field(..., ge=0, le=500, description="Weight in kilograms")


class HealthWeightRead(HealthWeightBase):
    """Schema for reading a health weight record.

    Extends HealthWeightBase with identifier fields required for retrieving
    and referencing weight records in the system.

    Attributes:
        source (Source | None): The source or device from which the weight data was obtained.
        id (uuid.UUID): Unique identifier for the weight record to update.
        user_id (StrictInt): Foreign key reference to the user.
    """

    source: Source = Field(default=Source.MANUAL, validate_default=True, description="Source of the weight data")
    id: uuid.UUID = Field(..., description="Unique identifier for the weight record to update")
    user_id: StrictInt = Field(..., description="Foreign key reference to the user")
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")
    updated_at: datetime = Field(..., description="When the record last changed, set by the server")


class HealthWeightUpdate(core_partial_update.NotClearable, HealthWeightWrite):
    """Schema for the fields a PATCH changes on a weight record.

    The record is named by the path, so the body carries neither an id nor an owner; only the
    fields present are changed.
    """

    not_clearable: ClassVar[tuple[str, ...]] = ("date", "weight_kg")


class HealthWeightImport(HealthWeightCreate):
    """Weight record written by the server itself: a provider sync or a profile import.

    Unlike :class:`HealthWeightCreate` it carries the provenance, which a client never sets. Every
    server-side writer of ``source`` takes ``Health<Kind>Import`` (create) or ``Health<Kind>ImportUpdate``.

    Attributes:
        source (Source): The source the record came from; ``manual`` when none is given.
    """

    source: Source = Field(default=Source.MANUAL, validate_default=True, description="Source of the weight data")


class HealthWeightImportUpdate(HealthWeightUpdate):
    """Fields a provider sync or a profile import changes on a weight record, provenance included.

    Attributes:
        source (Source | None): The source the record came from.
    """

    not_clearable: ClassVar[tuple[str, ...]] = (*HealthWeightUpdate.not_clearable, "source")

    source: Source | None = Field(default=None, description="Source of the weight data")
