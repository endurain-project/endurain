"""Pydantic schemas for activity exercise titles."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class ActivityExerciseTitles(BaseModel):
    """
    Schema describing an activity exercise title entry.

    Attributes:
        id: Optional database identifier.
        exercise_category: FIT exercise category code.
        exercise_name: FIT exercise name identifier.
        wkt_step_name: Workout step name (may include spaces).
    """

    id: StrictInt | None = None
    exercise_category: StrictInt
    exercise_name: StrictInt
    wkt_step_name: StrictStr = Field(..., max_length=250)

    model_config = ConfigDict(from_attributes=True)
