from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activity_workout_steps.models as activity_workout_steps_models
import activity_workout_steps.schema as activity_workout_steps_schema

import core.logger as core_logger
    

def create_activity_workout_steps(activity_workout_steps: list[activity_workout_steps_schema.ActivityWorkoutSteps], activity_id: int, db: Session):
    try:
        # Create a list to store the ActivityWorkoutSteps objects
        workout_steps = []

        # Iterate over the list of ActivityWorkoutSteps objects
        for step in activity_workout_steps:
            print(step)
            # Create an ActivitySplits object
            db_stream = activity_workout_steps_models.ActivityWorkoutSteps(
                activity_id=activity_id,
                message_index=step.message_index,
                duration_type=step.duration_type,
                duration_value=step.duration_value,
                target_type=step.target_type,
                target_value=step.target_value,
                intensity=step.intensity,
                notes=step.notes,
                exercise_name=step.exercise_name,
                exercise_weight=step.exercise_weight,
                weight_display_unit=step.weight_display_unit,
            )

            # Append the object to the list
            workout_steps.append(db_stream)

        # Bulk insert the list of ActivityWorkoutSteps objects
        db.bulk_save_objects(workout_steps)
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger(f"Error in create_activity_workout_steps: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
