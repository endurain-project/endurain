"""Activity workout steps schemas."""

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictFloat,
    StrictInt,
    StrictStr,
)

import core.pagination as core_pagination


class ActivityWorkoutStepsBase(BaseModel):
    """Fields that describe one workout step.

    Attributes:
        message_index: Workout step message index.
        duration_type: Workout step duration type.
        duration_value: Workout step duration value.
        target_type: Workout step target type.
        target_value: Workout step target value.
        intensity: Workout step intensity type.
        notes: Workout step notes.
        exercise_category: Workout step exercise
            category.
        exercise_name: Exercise name ID.
        exercise_weight: Workout step exercise weight.
        weight_display_unit: Workout step weight
            display unit.
        secondary_target_value: Workout step secondary
            target value.
    """

    message_index: StrictInt
    duration_type: StrictStr
    duration_value: StrictFloat | None = None
    target_type: StrictStr | None = None
    target_value: StrictInt | None = None
    intensity: StrictStr | None = None
    notes: StrictStr | None = None
    exercise_category: StrictInt | None = None
    exercise_name: StrictInt | None = None
    exercise_weight: StrictFloat | None = None
    weight_display_unit: StrictStr | None = None
    secondary_target_value: StrictStr | None = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class ActivityWorkoutStepsRead(ActivityWorkoutStepsBase):
    """A stored workout step, as the API returns it.

    Attributes:
        id: Primary key.
        activity_id: FK to activities table.
    """

    id: StrictInt
    activity_id: StrictInt


#: One page of an activity's planned workout steps. A structured workout's step
#: count has no domain ceiling, so the read is paginated.
ActivityWorkoutStepsPage = core_pagination.Page[ActivityWorkoutStepsRead]
