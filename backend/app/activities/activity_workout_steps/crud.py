from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.activity.schema as activities_schema
import activities.activity.models as activity_models
import activities.activity.crud as activity_crud

import activities.activity_workout_steps.models as activity_workout_steps_models
import activities.activity_workout_steps.schema as activity_workout_steps_schema

import server_settings.utils as server_settings_utils

import core.logger as core_logger


def get_activity_workout_steps(activity_id: int, token_user_id: int, db: Session):
    try:
        activity = activity_crud.get_activity_by_id(activity_id, db)

        if not activity:
            # If the activity does not exist, return None
            return None

        user_is_owner = True
        if token_user_id != activity.user_id:
            user_is_owner = False

        if not user_is_owner and activity.hide_workout_sets_steps:
            # If the user is not the owner and sets/steps are hidden, return None
            return None

        # Get the activity workout steps from the database
        activity_workout_steps = (
            db.query(activity_workout_steps_models.ActivityWorkoutSteps)
            .filter(
                activity_workout_steps_models.ActivityWorkoutSteps.activity_id
                == activity_id,
            )
            .all()
        )

        # Check if there are activity workout steps if not return None
        if not activity_workout_steps:
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


def get_activities_workout_steps(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    activities: list[activities_schema.Activity] = None,
):
    try:
        if not activity_ids:
            return []

        if not activities:
            activities = (
                db.query(activity_models.Activity)
                .filter(activity_models.Activity.id.in_(activity_ids))
                .all()
            )

        if not activities:
            return []

        # Build a map: activity_id -> activity
        activity_map = {activity.id: activity for activity in activities}

        # Determine which activity IDs the user is allowed to view steps for
        allowed_ids = [
            activity.id
            for activity in activities
            if activity.user_id == token_user_id or not activity.hide_workout_sets_steps
        ]

        if not allowed_ids:
            return []

        # Fetch workout steps for allowed activities
        workout_steps = (
            db.query(activity_workout_steps_models.ActivityWorkoutSteps)
            .filter(
                activity_workout_steps_models.ActivityWorkoutSteps.activity_id.in_(
                    allowed_ids
                )
            )
            .all()
        )

        if not workout_steps:
            return []

        return workout_steps

    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_activities_workout_steps: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_public_activity_workout_steps(activity_id: int, db: Session):
    try:
        activity = activity_crud.get_activity_by_id(activity_id, db)

        if not activity:
            # If the activity does not exist, return None
            return None

        if activity.hide_workout_sets_steps:
            # If the sets/steps are hidden, return None
            return None

        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_utils.get_server_settings_or_404(db)

        # Return None if public sharable links are disabled
        if not server_settings.public_shareable_links:
            return None

        # Get the activity workout steps from the database
        activity_workout_steps = (
            db.query(activity_workout_steps_models.ActivityWorkoutSteps)
            .join(
                activity_models.Activity,
                activity_models.Activity.id
                == activity_workout_steps_models.ActivityWorkoutSteps.activity_id,
            )
            .filter(
                activity_workout_steps_models.ActivityWorkoutSteps.activity_id
                == activity_id,
                activity_models.Activity.visibility == 0,
                activity_models.Activity.id == activity_id,
            )
            .all()
        )

        # Check if there are activity workout steps, if not return None
        if not activity_workout_steps:
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
                exercise_category=step.exercise_category,
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
