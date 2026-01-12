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


class HealthIntradayHeartrateBase(BaseModel):
    """
    Base model for health intraday heart_rate data.

    Represents the core attributes of a user's intraday heart rate record, including the user reference,
    timestamp of the record, measurement of heart rate taken, and the source of the data.

    Attributes:
        timestamp (datetime | None): Timestamp of the heart rate record. Optional field.
        heart_rate (StrictInt | None): Measurement of heart rate taken. Must be a non-negative integer. Optional field.
        source (Source | None): Source of the heart rate data (e.g., device, API, manual entry). Optional field.

    Configuration:
        - from_attributes: Allows model to be populated from ORM objects.
        - extra: Forbids any extra fields not defined in the model.
        - validate_assignment: Validates field values when assigned after model creation.
        - use_enum_values: Uses enum values instead of enum objects in serialization.
    """

    timestamp: datetime | None = Field(None, description="Timestamp of the heart rate")
    heart_rate: StrictInt | None = Field(None, ge=0, description="Measurement of heart rate taken")
    source: Source | None = Field(None, description="Source of the heart rate data")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthIntradayHeartrateCreate(HealthIntradayHeartrateBase):
    """
    Pydantic model for creating health intraday heart rate records.

    Automatically sets the timestamp to now if not provided during instance creation.

    Attributes:
        Inherits all attributes from HealthIntradayHeartrateBase.

    Validators:
        set_default_timestamp: Ensures that if no timestamp is provided, it defaults to now.
    """

    @model_validator(mode="after")
    def set_default_timestamp(self) -> "HealthIntradayHeartrateCreate":
        """Set timestamp to today if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()
        return self


class HealthIntradayHeartrateRead(HealthIntradayHeartrateBase):
    """
    Schema for reading health heart rate records.

    Extends the base health heart rate schema with an identifier field for retrieving
    or referencing existing heart rate records in the database.

    Attributes:
        id (StrictInt): Unique identifier for the heart rate record to update. Required field.
        user_id (StrictInt): Foreign key reference to the user. Required field.
    """

    id: StrictInt = Field(
        ..., description="Unique identifier for the heart rate record to update"
    )
    user_id: StrictInt = Field(..., description="Foreign key reference to the user")


class HealthIntradayHeartrateUpdate(HealthIntradayHeartrateRead):
    """
    Schema for updating health intraday heart rate records.

    Inherits from HealthIntradayHeartrateRead to maintain consistency with read operations
    while allowing modifications to health heart rate data. This schema is used for
    PUT/PATCH requests to update existing health heart rate entries.
    """


class HealthIntradayHeartrateListResponse(BaseModel):
    """
    Response model for listing health heart rate records.

    Attributes:
        num_records (StrictInt | None): Number of records in this response.
        page_number (StrictInt | None): Current page number.
        records (list[HealthIntradayHeartrateRead]): List of health heart rate records.
    """
    num_records: StrictInt | None = Field(
        None, description="Number of records in this response"
    )
    page_number: StrictInt | None = Field(None, description="Current page number")
    records: list[HealthIntradayHeartrateRead] = Field(
        ..., description="List of health heart rate records"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
