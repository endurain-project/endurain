import os

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


def get_activities_media(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    activities: list[activities_schema.Activity] = None,
):
    try:
        if not activity_ids:
            return []

        if not activities:
            # Fetch all activities at once
            activities = (
                db.query(activity_models.Activity)
                .filter(activity_models.Activity.id.in_(activity_ids))
                .all()
            )

        if not activities:
            return []

        # Filter out hidden media for activities the user doesn't own
        allowed_ids = [
            activity.id for activity in activities if activity.user_id == token_user_id
        ]

        if not allowed_ids:
            return []

        # Fetch all media for allowed activities
        activity_media = (
            db.query(activity_media_models.ActivityMedia)
            .filter(activity_media_models.ActivityMedia.activity_id.in_(allowed_ids))
            .all()
        )

        if not activity_media:
            return []

        return activity_media

    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_activities_media: {err}", "error", exc=err
        )
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


def create_activity_medias(
    activity_media: list[activity_media_schema.ActivityMedia],
    activity_id: int,
    db: Session,
):
    try:
        # Create a list to store the ActivityMedia objects
        media = []

        # Iterate over the list of ActivityMedia objects
        for media_item in activity_media:
            # Create an ActivityMedia object
            db_media = activity_media_models.ActivityMedia(
                activity_id=activity_id,
                **{
                    key: getattr(media_item, key)
                    for key in [
                        "media_path",
                        "media_type",
                    ]
                },
            )

            # Append the object to the list
            media.append(db_media)

        # Bulk insert the list of ActivityMedia objects
        db.bulk_save_objects(media)
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_activity_medias: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_activity_media(activity_media_id: int, token_user_id: int, db: Session):
    try:
        # Get the activity media from the database
        activity_media = (
            db.query(activity_media_models.ActivityMedia)
            .filter(activity_media_models.ActivityMedia.id == activity_media_id)
            .first()
        )

        if not activity_media:
            # If the activity media does not exist, raise a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity media not found",
            )

        activity = activity_crud.get_activity_by_id_from_user_id(
            activity_media.activity_id, token_user_id, db
        )

        if not activity:
            # If the activity does not exist, raise a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        # Check if the user is the owner of the activity
        if activity.user_id != token_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this media",
            )

        # Delete the activity media from the database
        db.delete(activity_media)
        db.commit()

        # Remove the media file from the filesystem
        if os.path.exists(activity_media.media_path):
            os.remove(activity_media.media_path)

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in delete_activity_media: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
