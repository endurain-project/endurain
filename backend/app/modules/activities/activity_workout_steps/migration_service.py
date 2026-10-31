"""The workout-step operations exposed only to data migrations."""

from sqlalchemy.orm import Session

import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud


def create_activity_workout_steps(
    activity_workout_steps: list[activity_workout_steps_contracts.ActivityWorkoutStepsCreate],
    activity_id: int,
    db: Session,
) -> None:
    """Create workout steps for an activity and commit them, as migrations did.

    Args:
        activity_workout_steps: Steps to store.
        activity_id: The parent activity ID.
        db: Database session.
    """
    activity_workout_steps_crud.create_activity_workout_steps(activity_workout_steps, activity_id, db)
    db.commit()
