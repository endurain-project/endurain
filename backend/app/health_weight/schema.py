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


class HealthWeight(BaseModel):
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
