"""Pydantic request and response shapes for health steps records."""

from datetime import date as datetime_date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, StrictInt

import modules.health.schema as health_schema


class Source(Enum):
    """An enumeration representing supported sources for the application.

    Members:
        GARMIN: Garmin health data source
    """

    GARMIN = "garmin"


class HealthStepsBase(BaseModel):
    """Base model for health steps data.

    Represents the core attributes of a user's step count record, including the user reference,
    date of the record, number of steps taken, and the source of the data.

    Attributes:
        date (datetime_date | None): Calendar date of the steps record. Optional field.
        steps (StrictInt | None): Number of steps taken. Must be a non-negative integer. Optional field.
        source (Source | None): Source of the steps data (e.g., device, API, manual entry). Optional field.

    Configuration:
        - from_attributes: Allows model to be populated from ORM objects.
        - extra: Forbids any extra fields not defined in the model.
        - validate_assignment: Validates field values when assigned after model creation.
        - use_enum_values: Uses enum values instead of enum objects in serialization.
    """

    date: datetime_date | None = Field(default=None, description="Calendar date of the steps")
    steps: StrictInt | None = Field(default=None, ge=0, description="Number of steps taken")
    source: Source | None = Field(default=None, description="Source of the steps data")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthStepsCreate(HealthStepsBase):
    """Schema for creating a health steps record.

    The date is optional; ``service`` fills it in when the client sends none.
    """


class HealthStepsRead(HealthStepsBase):
    """Schema for reading health steps records.

    Extends the base health steps schema with an identifier field for retrieving
    or referencing existing steps records in the database.

    Attributes:
        id (StrictInt): Unique identifier for the steps record to update. Required field.
        user_id (StrictInt): Foreign key reference to the user. Required field.
    """

    id: StrictInt = Field(..., description="Unique identifier for the steps record to update")
    user_id: StrictInt = Field(..., description="Foreign key reference to the user")


class HealthStepsUpdate(HealthStepsRead):
    """Schema for updating health steps records.

    Inherits from HealthStepsRead to maintain consistency with read operations
    while allowing modifications to health steps data. This schema is used for
    PUT/PATCH requests to update existing health steps entries.
    """


class HealthStepsListResponse(health_schema.HealthListResponse):
    """Response model for listing health steps records.

    Extends the base HealthListResponse to provide a typed response containing
    a list of steps records. This model is used when returning multiple steps
    entries from API endpoints.

    Attributes:
        records: A list of HealthStepsRead objects representing individual
            steps records.
    """

    records: list[HealthStepsRead] = Field(..., description="List of health steps records")
