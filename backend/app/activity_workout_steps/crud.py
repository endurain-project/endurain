from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.models as activities_models

import activity_workout_steps.models as activity_workout_steps_models
import activity_workout_steps.schema as activity_workout_steps_schema

import server_settings.crud as server_settings_crud

import core.logger as core_logger


def get_activity_workout_steps(activity_id: int, db: Session):
    try:
        # Get the activity workout steps from the database
        activity_workout_steps = (
            db.query(activity_workout_steps_models.ActivityWorkoutSteps)
            .filter(
                activity_workout_steps_models.ActivityWorkoutSteps.activity_id == activity_id,
            )
            .all()
        )

        # Check if there are activity workout steps if not return None
        if not activity_workout_steps:
            return None
        
        # Get the activity from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.id == activity_id,
            )
            .first()
        )

        # Check if the activity exists, if not return None
        if not activity:
            return None

        # Return the activity laps
        return activity_workout_steps
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_workout_steps: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
    

def get_public_activity_workout_steps(activity_id: int, db: Session):
    try:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_crud.get_server_settings(db)

        # Return None if public sharable links are disabled
        if not server_settings or not server_settings.public_shareable_links:
            return None
        
        # Get the activity workout steps from the database
        activity_workout_steps = (
            db.query(activity_workout_steps_models.ActivityWorkoutSteps)
            .join(
                activities_models.Activity,
                activities_models.Activity.id
                == activity_workout_steps_models.ActivityWorkoutSteps.activity_id,
            )
            .filter(
                activity_workout_steps_models.ActivityWorkoutSteps.activity_id == activity_id,
                activities_models.Activity.visibility == 0,
                activities_models.Activity.id
                == activity_id,
            )
            .all()
        )

        # Check if there are activity workout steps, if not return None
        if not activity_workout_steps:
            return None
        
        # Get the activity from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.id == activity_id,
            )
            .first()
        )

        # Check if the activity exists, if not return None
        if not activity:
            return None

        # Return the activity laps
        return activity_workout_steps
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_public_activity_workout_steps: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_activity_workout_steps(
    activity_workout_steps: list[activity_workout_steps_schema.ActivityWorkoutSteps],
    activity_id: int,
    db: Session,
):
    try:
        # Create a list to store the ActivityWorkoutSteps objects
        workout_steps = []

        # Iterate over the list of ActivityWorkoutSteps objects
        for step in activity_workout_steps:
            # Create an ActivityWorkoutSteps object
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
                secondary_target_value=step.secondary_target_value,
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
