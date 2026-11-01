"""Pydantic schemas for activity exercise titles."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

import core.pagination as core_pagination

#: Bounds of the PostgreSQL ``INTEGER`` columns that store the FIT exercise category and name codes.
_INT4_MIN = -(2**31)
_INT4_MAX = 2**31 - 1


class ActivityExerciseTitlesBase(BaseModel):
    """Fields that describe an exercise title.

    Attributes:
        exercise_category: FIT exercise category code.
        exercise_name: FIT exercise name identifier.
        wkt_step_name: Workout step name (may include spaces).
    """

    exercise_category: StrictInt = Field(..., ge=_INT4_MIN, le=_INT4_MAX)
    exercise_name: StrictInt = Field(..., ge=_INT4_MIN, le=_INT4_MAX)
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
