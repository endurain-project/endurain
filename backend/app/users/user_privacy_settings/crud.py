from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import users.user_privacy_settings.schema as user_privacy_settings_schema
import users.user_privacy_settings.models as user_privacy_settings_models

import core.logger as core_logger


def get_user_privacy_settings_by_user_id(user_id: int, db: Session):
    try:
        # Get the user privacy settings by the user id
        user_privacy_settings = (
            db.query(user_privacy_settings_models.UsersPrivacySettings)
            .filter(
                user_privacy_settings_models.UsersPrivacySettings.user_id == user_id
            )
            .first()
        )

        # Check if user_privacy_settings is None and return None if it is
        if user_privacy_settings is None:
            # If the user was not found, return a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User privacy settings not found",
            )

        # Return the user privacy settings
        return user_privacy_settings
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_privacy_settings_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_user_privacy_settings(user_id: int, db: Session):
    try:
        # Create a new user privacy settings
        user_privacy_settings = user_privacy_settings_models.UsersPrivacySettings(
            user_id=user_id,
            default_activity_visibility=0,
            hide_activity_start_time=False,
            hide_activity_location=False,
            hide_activity_map=False,
            hide_activity_hr=False,
            hide_activity_power=False,
            hide_activity_cadence=False,
            hide_activity_elevation=False,
            hide_activity_speed=False,
            hide_activity_pace=False,
            hide_activity_laps=False,
            hide_activity_workout_sets_steps=False,
            hide_activity_gear=False,
        )

        # Add the user privacy settings to the database
        db.add(user_privacy_settings)
        db.commit()
        db.refresh(user_privacy_settings)

        # Return the user privacy settings
        return user_privacy_settings
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_user_privacy_settings: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_user_privacy_settings(
    user_id: int,
    user_privacy_settings_data: user_privacy_settings_schema.UsersPrivacySettings,
    db: Session,
):
    try:
        # Get the user privacy settings by the user id
        db_user_privacy_settings = get_user_privacy_settings_by_user_id(user_id, db)

        # Dictionary of the fields to update if they are not None
        user_privacy_settings_data = user_privacy_settings_data.model_dump(
            exclude_unset=True
        )
        # Iterate over the fields and update the db_user dynamically
        for key, value in user_privacy_settings_data.items():
            setattr(db_user_privacy_settings, key, value)

        # Commit the changes to the database
        db.commit()
        db.refresh(db_user_privacy_settings)

        # Return the updated user privacy settings
        return db_user_privacy_settings
    except HTTPException:
        raise
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in edit_user_privacy_settings: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
