from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import activities.activity.schema as activities_schema
import activities.activity.models as activity_models
import activities.activity.crud as activity_crud

import activities.activity_media.models as activity_media_models
import activities.activity_media.schema as activity_media_schema

import server_settings.crud as server_settings_crud

import core.logger as core_logger


def get_activity_media(activity_id: int, token_user_id: int, db: Session):
    try:
        activity = activity_crud.get_activity_by_id_from_user_id(
            activity_id, token_user_id, db
        )

        if not activity:
            # If the activity does not exist, return None
            return None

        """ user_is_owner = True
        if token_user_id != activity.user_id:
            user_is_owner = False

        if not user_is_owner and activity.hide_laps:
            # If the user is not the owner and laps are hidden, return None
            return None """

        # Get the activity media from the database
        activity_media = (
            db.query(activity_media_models.ActivityMedia)
            .filter(
                activity_media_models.ActivityMedia.activity_id == activity_id,
            )
            .all()
        )

        # Check if there are activity media if not return None
        if not activity_media:
            return None

        # Return the activity media
        return activity_media
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_media: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_activity_media(activity_id: int, media_path: str, db: Session):
    try:
        # Create a new activity_media
        db_activity_media = activity_media_models.ActivityMedia(
            activity_id=activity_id,
            media_path=media_path,
            media_type=1,
        )

        # Add the activity_media to the database
        db.add(db_activity_media)
        db.commit()
        db.refresh(db_activity_media)

        # Return activity_media
        return db_activity_media
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if path and file name are unique.",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_activity_media: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
