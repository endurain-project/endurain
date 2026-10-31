"""
Pydantic schemas for health water intake data.

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
    model_validator,
)

import core.config as core_config
import core.timezone as core_timezone
import modules.health.schema as health_schema


class Source(Enum):
    """
    Enumeration of data sources for water intake records.

    Attributes:
        MANUAL: Manually entered water intake data.
        GARMIN: Garmin fitness tracking platform as a data source.
    """

    MANUAL = "manual"
    GARMIN = "garmin"


class HealthWaterBase(BaseModel):
    """
    Base model for health water intake data.

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
    """
    Schema for creating a new water intake record.

    Automatically sets the date to today if not provided.
    """

    @model_validator(mode="after")
    def set_default_date(self) -> "HealthWaterCreate":
        """
        Set date to today if not provided.

        Clients should always send their own local date — the request carries no
        timezone, so this fallback can only use the server's configured zone and
        will file an entry logged near local midnight under the wrong day for an
        athlete elsewhere. Resolved through ``settings.TZ`` explicitly rather
        than ``date.today()``, which silently depends on the container's clock.

        Returns:
            The validated model instance with date set.
        """
        if self.date is None:
            self.date = core_timezone.today_in(core_config.settings.TZ)
        return self


class HealthWaterRead(HealthWaterBase):
    """
    Schema for reading a water intake record.

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


class HealthWaterUpdate(HealthWaterRead):
    """
    Schema for updating a water intake record.

    Inherits from HealthWaterRead for consistency with read
    operations while allowing modifications to water intake data.
    """


class HealthWaterListResponse(health_schema.HealthListResponse):
    """
    Response model for listing health water intake records.

    Attributes:
        records: A list of HealthWaterRead objects representing
            individual water intake records.
    """

    records: list[HealthWaterRead] = Field(
        ...,
        description="List of health water intake records",
    )
