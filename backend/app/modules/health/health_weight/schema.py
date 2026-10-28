"""Pydantic request and response shapes for health weight records."""

from datetime import date as datetime_date
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    field_validator,
)


class Source(Enum):
    """Enumeration of data sources for health weight records.

    Attributes:
        GARMIN: Garmin fitness tracking platform as a data source.
    """

    GARMIN = "garmin"


class HealthWeightBase(BaseModel):
    """Pydantic model for health weight data.

    This model defines the structure and validation rules for health weight information,
    including body composition metrics and related health indicators.

    Attributes:
        date (datetime_date | None): The date of the health weight measurement.
        weight (StrictFloat | None): Weight in kilograms. Must be between 0 and 500.
        bmi (StrictFloat | None): Body Mass Index value. Must be between 0 and 100.
        body_fat (StrictFloat | None): Body fat percentage. Must be between 0 and 100.
        body_water (StrictFloat | None): Body water percentage. Must be between 0 and 100.
        bone_mass (StrictFloat | None): Bone mass in kilograms. Must be between 0 and 500.
        muscle_mass (StrictFloat | None): Muscle mass in kilograms. Must be between 0 and 500.
        physique_rating (StrictInt | None): Physique rating score. Must be greater than or equal to 0.
        visceral_fat (StrictFloat | None): Visceral fat percentage. Must be between 0 and 100.
        metabolic_age (StrictInt | None): Metabolic age in years. Must be between 0 and 120.
        source (Source | None): The source or device from which the weight data was obtained.

    Model Configuration:
        - Populates from ORM attributes
        - Forbids extra fields
        - Validates assignments
        - Uses enum values for serialization
    """

    date: datetime_date | None = Field(default=None, description="Health weight date (date)")
    weight: StrictFloat | None = Field(default=None, ge=0, le=500, description="Weight in kilograms")
    bmi: StrictFloat | None = Field(default=None, ge=0, le=100, description="Body Mass Index")
    body_fat: StrictFloat | None = Field(default=None, ge=0, le=100, description="Body fat percentage")
    body_water: StrictFloat | None = Field(default=None, ge=0, le=100, description="Body water percentage")
    bone_mass: StrictFloat | None = Field(default=None, ge=0, le=500, description="Bone mass in kilograms")
    muscle_mass: StrictFloat | None = Field(default=None, ge=0, le=500, description="Muscle mass in kilograms")
    physique_rating: StrictInt | None = Field(default=None, ge=0, description="Physique rating")
    visceral_fat: StrictFloat | None = Field(default=None, ge=0, le=100, description="Visceral fat")
    metabolic_age: StrictInt | None = Field(default=None, ge=0, le=120, description="Metabolic age")
    source: Source | None = Field(default=None, description="Source of the weight data")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthWeightCreate(HealthWeightBase):
    """Schema for creating a health weight record.

    The date is optional; ``service`` fills it in when the client sends none.
    """

    weight: StrictFloat = Field(..., ge=0, le=500, description="Weight in kilograms")


class HealthWeightRead(HealthWeightBase):
    """Schema for reading a health weight record.

    Extends HealthWeightBase with identifier fields required for retrieving
    and referencing weight records in the system.

    Attributes:
        id (StrictInt): Unique identifier for the weight record to update.
        user_id (StrictInt): Foreign key reference to the user.
    """

    id: StrictInt = Field(..., description="Unique identifier for the weight record to update")
    user_id: StrictInt = Field(..., description="Foreign key reference to the user")
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")


class HealthWeightUpdate(HealthWeightBase):
    """Schema for the fields a PATCH changes on a weight record.

    The record is named by the path, so the body carries neither an id nor an owner; only the
    fields present are changed.
    """

    @field_validator("weight")
    @classmethod
    def _weight_is_not_cleared(cls, value: object) -> object:
        """Refuse to clear the weight, which every record has.

        Args:
            value: The weight in the edit.

        Returns:
            The weight.

        Raises:
            ValueError: When the edit sets the weight to null.
        """
        if value is None:
            raise ValueError("weight cannot be cleared")
        return value
