"""Pydantic schemas for activity exercise titles."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import core.pagination as core_pagination


class ActivityExerciseTitlesBase(BaseModel):
    """Fields that describe an exercise title.

    Attributes:
        exercise_category: FIT exercise category code.
        exercise_name: FIT exercise name identifier.
        wkt_step_name: Workout step name (may include spaces).
    """

    exercise_category: StrictInt
    exercise_name: StrictInt
    wkt_step_name: StrictStr = Field(..., max_length=250)

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ActivityExerciseTitlesRead(ActivityExerciseTitlesBase):
    """A stored exercise title, as the API returns it.

    Attributes:
        id: Database identifier.
    """

    id: StrictInt


#: One page of the exercise-title catalogue.
ActivityExerciseTitlesPage = core_pagination.Page[ActivityExerciseTitlesRead]
