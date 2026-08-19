"""Public persistence operations for activity workout steps."""

from sqlalchemy.orm import Session

import modules.activities.activity_workout_steps.crud as workout_steps_crud
import modules.activities.activity_workout_steps.schema as workout_steps_schema


def list_workout_steps_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[workout_steps_schema.ActivityWorkoutSteps]:
    """Return workout steps for activity IDs already scoped by the caller."""
    return workout_steps_crud.get_activities_workout_steps(activity_ids, db)


def store_workout_steps(
    steps: list[workout_steps_schema.ActivityWorkoutSteps],
    activity_id: int,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """Store parsed workout steps for an activity."""
    workout_steps_crud.create_activity_workout_steps(steps, activity_id, db, commit=commit)
