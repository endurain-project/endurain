from enum import Enum
from pydantic import BaseModel, ConfigDict, StrictInt, Field, model_validator
from datetime import datetime


class Source(Enum):
    """
    An enumeration representing supported sources for the application.

    Members:
        GARMIN: Garmin health data source
    """

    GARMIN = "garmin"


class HealthIntradayStepsBase(BaseModel):
    """
    Base model for health intraday steps data.

    Represents the core attributes of a user's intraday step count record, including the user reference,
    timestamp of the record, number of steps taken, and the source of the data.

    Attributes:
        timestamp (datetime | None): Timestamp of the steps record. Optional field.
        steps (StrictInt | None): Number of steps taken. Must be a non-negative integer. Optional field.
        source (Source | None): Source of the steps data (e.g., device, API, manual entry). Optional field.

    Configuration:
        - from_attributes: Allows model to be populated from ORM objects.
        - extra: Forbids any extra fields not defined in the model.
        - validate_assignment: Validates field values when assigned after model creation.
        - use_enum_values: Uses enum values instead of enum objects in serialization.
    """

    timestamp: datetime | None = Field(None, description="Timestamp of the steps")
    steps: StrictInt | None = Field(None, ge=0, description="Number of steps taken")
    source: Source | None = Field(None, description="Source of the steps data")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthIntradayStepsCreate(HealthIntradayStepsBase):
    """
    Pydantic model for creating health intraday steps records.

    Automatically sets the timestamp to now if not provided during instance creation.

    Attributes:
        Inherits all attributes from HealthIntradayStepsBase.

    Validators:
        set_default_timestamp: Ensures that if no timestamp is provided, it defaults to now.
    """

    @model_validator(mode="after")
    def set_default_timestamp(self) -> "HealthIntradayStepsCreate":
        """Set timestamp to today if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()
        return self


class HealthIntradayStepsRead(HealthIntradayStepsBase):
    """
    Schema for reading health steps records.

    Extends the base health steps schema with an identifier field for retrieving
    or referencing existing steps records in the database.

    Attributes:
        id (StrictInt): Unique identifier for the steps record to update. Required field.
        user_id (StrictInt): Foreign key reference to the user. Required field.
    """

    id: StrictInt = Field(
        ..., description="Unique identifier for the steps record to update"
    )
    user_id: StrictInt = Field(..., description="Foreign key reference to the user")


class HealthIntradayStepsUpdate(HealthIntradayStepsRead):
    """
    Schema for updating health intraday steps records.

    Inherits from HealthIntradayStepsRead to maintain consistency with read operations
    while allowing modifications to health steps data. This schema is used for
    PUT/PATCH requests to update existing health steps entries.
    """


class HealthIntradayStepsListResponse(BaseModel):
    """
    Response model for listing health steps records.

    Attributes:
        total (StrictInt): Total number of steps records for the user.
        num_records (StrictInt | None): Number of records in this response.
        page_number (StrictInt | None): Current page number.
        records (list[HealthIntradayStepsRead]): List of health steps records.
    """

    total: StrictInt = Field(
        ..., description="Total number of steps records for the user"
    )
    num_records: StrictInt | None = Field(
        None, description="Number of records in this response"
    )
    page_number: StrictInt | None = Field(None, description="Current page number")
    records: list[HealthIntradayStepsRead] = Field(
        ..., description="List of health steps records"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
