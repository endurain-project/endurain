"""Pydantic schemas for health water intake data.

This module defines the request/response schemas for water intake
tracking, including validation rules and source enumeration.
"""

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
        source: Source of the water intake data.
    """

    date: datetime_date | None = Field(
        default=None,
        description="Calendar date of the water intake",
    )
    amount_ml: StrictFloat | None = Field(
        default=None,
        ge=0,
        le=20000,
        description="Water consumed in milliliters",
    )
    source: Source | None = Field(
        default=None,
        description="Source of the water intake data",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthWaterCreate(HealthWaterBase):
    """Schema for creating a new water intake record.

    The date is optional; ``service`` fills it in when the client sends none.
    """

    amount_ml: StrictFloat = Field(..., ge=0, le=20000, description="Water consumed in milliliters")


class HealthWaterRead(HealthWaterBase):
    """Schema for reading a water intake record.

    Attributes:
        id: Unique identifier for the water intake record.
        user_id: Foreign key reference to the user.
    """

    id: StrictInt = Field(
        ...,
        description=("Unique identifier for the water intake record"),
    )
    user_id: StrictInt = Field(
        ...,
        description="Foreign key reference to the user",
    )
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")


class HealthWaterUpdate(HealthWaterBase):
    """Schema for the fields a PATCH changes on a water record.

    The record is named by the path, so the body carries neither an id nor an owner; only the
    fields present are changed.
    """

    @field_validator("amount_ml")
    @classmethod
    def _amount_ml_is_not_cleared(cls, value: object) -> object:
        """Refuse to clear the amount, which every record has.

        Args:
            value: The amount in the edit.

        Returns:
            The amount.

        Raises:
            ValueError: When the edit sets the amount to null.
        """
        if value is None:
            raise ValueError("amount_ml cannot be cleared")
        return value
