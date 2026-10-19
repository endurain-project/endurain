"""ORM↔schema transformation for activity workout steps.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts
import modules.activities.activity_workout_steps.models as activity_workout_steps_models
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema


def to_read_schema(
    orm_step: activity_workout_steps_models.ActivityWorkoutSteps,
) -> activity_workout_steps_schema.ActivityWorkoutStepsRead:
    """Convert an ORM row to its read schema.

    Args:
        orm_step: The ORM row to convert.

    Returns:
        The read schema.
    """
    return activity_workout_steps_schema.ActivityWorkoutStepsRead.model_validate(orm_step)


def to_orm(
    step: activity_workout_steps_contracts.ActivityWorkoutStepsCreate,
    activity_id: int,
) -> activity_workout_steps_models.ActivityWorkoutSteps:
    """Build an ORM row from a workout step schema.

    Args:
        step: The workout step schema.
        activity_id: The parent activity ID.

    Returns:
        An unsaved ActivityWorkoutSteps ORM instance.
    """
    return activity_workout_steps_models.ActivityWorkoutSteps(
        activity_id=activity_id,
        message_index=step.message_index,
        duration_type=step.duration_type,
        duration_value=step.duration_value,
        target_type=step.target_type,
        target_value=step.target_value,
        intensity=step.intensity,
        notes=step.notes,
        exercise_category=step.exercise_category,
        exercise_name=step.exercise_name,
        exercise_weight=step.exercise_weight,
        weight_display_unit=step.weight_display_unit,
        secondary_target_value=step.secondary_target_value,
    )
