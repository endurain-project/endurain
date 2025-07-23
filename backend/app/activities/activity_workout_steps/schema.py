from pydantic import BaseModel


class ActivityWorkoutSteps(BaseModel):
    id: int | None = None
    activity_id: int | None = None
    message_index: int
    duration_type: str
    duration_value: float | None = None
    target_type: str | None = None
    target_value: int | None = None
    intensity: str | None = None
    notes: str | None = None
    exercise_category: int | None = None
    exercise_name: int | None = None
    exercise_weight: float | None = None
    weight_display_unit: str | None = None
    secondary_target_value: str | None = None

    model_config = {
        "from_attributes": True
    }