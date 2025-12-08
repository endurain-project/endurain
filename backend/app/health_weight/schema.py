from enum import Enum
from pydantic import BaseModel, ConfigDict
from datetime import date as datetime_date


class Source(Enum):
    """
    Enumeration representing the source of health weight data.

    Attributes:
        GARMIN (str): Indicates that the weight data comes from Garmin devices or services.
    """

    GARMIN = "garmin"


class HealthWeight(BaseModel):
    """
    Schema for health weight measurements.

    This class represents a comprehensive set of body composition and health metrics
    for a user at a specific point in time.

    Attributes:
        id (int | None): Unique identifier for the health weight record.
        user_id (int | None): Identifier of the user associated with this measurement.
        date (datetime_date | None): Date when the measurement was taken.
        weight (float | None): Body weight measurement.
        bmi (float | None): Body Mass Index calculated from height and weight.
        body_fat (float | None): Body fat percentage.
        body_water (float | None): Body water percentage.
        bone_mass (float | None): Bone mass measurement.
        muscle_mass (float | None): Muscle mass measurement.
        physique_rating (int | None): Overall physique rating score.
        visceral_fat (float | None): Visceral fat level measurement.
        metabolic_age (int | None): Estimated metabolic age based on body composition.
        source (Source | None): Source or origin of the measurement data.

    Configuration:
        - from_attributes: Enables population from ORM models
        - extra: Forbids extra fields not defined in the schema
        - validate_assignment: Validates values on assignment
        - use_enum_values: Uses enum values instead of enum instances
    """

    id: int | None = None
    user_id: int | None = None
    date: datetime_date | None = None
    weight: float | None = None
    bmi: float | None = None
    body_fat: float | None = None
    body_water: float | None = None
    bone_mass: float | None = None
    muscle_mass: float | None = None
    physique_rating: int | None = None
    visceral_fat: float | None = None
    metabolic_age: int | None = None
    source: Source | None = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthWeightListResponse(BaseModel):
    """
    Response schema for health weight list with total count.

    This class wraps a list of health weight records along with the total count,
    number of records, and page number providing a complete response for list endpoints.

    Attributes:
        total (int): Total number of weight records for the user.
        num_records (int | None): Number of records returned in this response.
        page_number (int | None): Page number of the current response.
        records (list[HealthWeight]): List of health weight measurements.

    Configuration:
        - from_attributes: Enables population from ORM models
        - extra: Forbids extra fields not defined in the schema
        - validate_assignment: Validates values on assignment
    """

    total: int
    num_records: int | None = None
    page_number: int | None = None
    records: list[HealthWeight]

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
