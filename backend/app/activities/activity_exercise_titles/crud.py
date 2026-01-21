from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import activities.activity_exercise_titles.models as activity_exercise_titles_models
import activities.activity_exercise_titles.schema as activity_exercise_titles_schema

import server_settings.utils as server_settings_utils

import core.logger as core_logger


def get_activity_exercise_titles(db: Session):
    try:
        # Get the activity exercise titles from the database
        activity_exercise_titles = db.query(
            activity_exercise_titles_models.ActivityExerciseTitles
        ).all()

        # Check if there are activity exercise titles if not return None
        if not activity_exercise_titles:
            return None

        # Return the activity exercise titles
        return activity_exercise_titles
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_exercise_titles: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_public_activity_exercise_titles(db: Session):
    try:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_utils.get_server_settings_or_404(db)

        # Return None if public sharable links are disabled
        if not server_settings.public_shareable_links:
            return None

        # Get the activity exercise titles from the database
        return get_activity_exercise_titles(db)
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_public_activity_exercise_titles: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_exercise_title_by_exercise_name(exercise_name: int, db: Session):
    try:
        # Get the activity exercise title from the database
        activity_exercise_title = db.query(
            activity_exercise_titles_models.ActivityExerciseTitles.filter(
                activity_exercise_titles_models.ActivityExerciseTitles.exercise_name
                == exercise_name,
            )
        ).first()

        # Check if there are activity exercise title if not return None
        if not activity_exercise_title:
            return None

        # Return the activity exercise title
        return activity_exercise_title
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_exercise_title_by_exercise_name: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_activity_exercise_titles(
    activity_exercise_titles: list[
        activity_exercise_titles_schema.ActivityExerciseTitles
    ],
    db: Session,
):
    try:
        # Create a list to store the ActivityExerciseTitles objects
        exercise_titles = []

        for exercise_title in activity_exercise_titles:
            # Check if exercise_name already exists
            existing_entry = (
                db.query(activity_exercise_titles_models.ActivityExerciseTitles)
                .filter_by(
                    exercise_name=exercise_title.exercise_name,
                    exercise_category=exercise_title.exercise_category,
                )
                .first()
            )

            if existing_entry:
                # Skip if exercise_name already exists
                continue

            # Create a new ActivityExerciseTitles object
            new_entry = activity_exercise_titles_models.ActivityExerciseTitles(
                exercise_category=exercise_title.exercise_category,
                exercise_name=exercise_title.exercise_name,
                wkt_step_name=exercise_title.wkt_step_name,
            )

            exercise_titles.append(new_entry)

        if exercise_titles:
            db.bulk_save_objects(exercise_titles)
            db.commit()
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if exercise_name is unique",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger(
            f"Error in create_activity_exercise_titles: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
