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
