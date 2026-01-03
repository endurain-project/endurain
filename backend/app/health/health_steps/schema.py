from enum import Enum
from pydantic import BaseModel, ConfigDict
from datetime import date as datetime_date


class Source(Enum):
    """
    An enumeration representing supported sources for the application.

    Members:
        GARMIN: Garmin health data source
    """

    GARMIN = "garmin"


class HealthSteps(BaseModel):
    """
    Pydantic model for health steps data.

    Attributes:
        id (int | None): Unique identifier for the health steps record. Defaults to None.
        user_id (int | None): ID of the user associated with the steps record. Defaults to None.
        date (datetime_date | None): Date when the steps were recorded. Defaults to None.
        steps (int | None): Number of steps recorded. Defaults to None.
        source (Source | None): Source from which the steps data was obtained. Defaults to None.

    Configuration:
        - from_attributes: Allows creation from ORM model attributes
        - extra: Forbids extra fields not defined in the model
        - validate_assignment: Validates field values on assignment
        - use_enum_values: Uses enum values instead of enum instances
    """

    id: int | None = None
    user_id: int | None = None
    date: datetime_date | None = None
    steps: int | None = None
    source: Source | None = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthStepsListResponse(BaseModel):
    """
    Response schema for health steps list with total count.

    This class wraps a list of health steps records along with the total count,
    number of records, and page number providing a complete response for list endpoints.

    Attributes:
        total (int): Total number of steps records for the user.
        num_records (int | None): Number of records returned in this response.
        page_number (int | None): Page number of the current response.
        records (list[HealthSteps]): List of health steps measurements.

    Configuration:
        - from_attributes: Enables population from ORM models
        - extra: Forbids extra fields not defined in the schema
        - validate_assignment: Validates values on assignment
    """

    total: int
    num_records: int | None = None
    page_number: int | None = None
    records: list[HealthSteps]

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
