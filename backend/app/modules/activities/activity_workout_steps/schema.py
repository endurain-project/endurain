"""Activity workout steps schemas."""

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictFloat,
    StrictInt,
    StrictStr,
)


class ActivityWorkoutSteps(BaseModel):
    """
    Activity workout step schema.

    Attributes:
        id: Primary key.
        activity_id: FK to activities table.
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

    id: StrictInt | None = None
    activity_id: StrictInt | None = None
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
    )
