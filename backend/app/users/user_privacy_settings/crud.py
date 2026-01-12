"""CRUD operations for user privacy settings."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import users.user_privacy_settings.schema as users_privacy_settings_schema
import users.user_privacy_settings.models as users_privacy_settings_models

import core.logger as core_logger


def get_user_privacy_settings_by_user_id(
    user_id: int, db: Session
) -> users_privacy_settings_models.UsersPrivacySettings | None:
    """
    Retrieve privacy settings for a specific user.

    Args:
        user_id: The ID of the user to fetch settings for.
        db: SQLAlchemy database session.

    Returns:
        The UsersPrivacySettings model if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    try:
        # Get the user privacy settings by the user id
        stmt = select(users_privacy_settings_models.UsersPrivacySettings).where(
            users_privacy_settings_models.UsersPrivacySettings.user_id == user_id
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in " f"get_user_privacy_settings_by_user_id: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def create_user_privacy_settings(
    user_id: int, db: Session
) -> users_privacy_settings_models.UsersPrivacySettings:
    """
    Create privacy settings for a user.

    Args:
        user_id: The ID of the user to create settings for.
        db: SQLAlchemy database session.

    Returns:
        The created UsersPrivacySettings model.

    Raises:
        HTTPException: 409 error if settings already exist.
        HTTPException: 500 error if database operation fails.
    """
    try:
        # Create a new user privacy settings with model defaults
        db_privacy_settings = users_privacy_settings_models.UsersPrivacySettings(
            user_id=user_id,
        )

        # Add the user privacy settings to the database
        db.add(db_privacy_settings)
        db.commit()
        db.refresh(db_privacy_settings)

        # Return the user privacy settings
        return db_privacy_settings
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Privacy settings already exist for this user",
        ) from integrity_error
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in create_user_privacy_settings: " f"{db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def edit_user_privacy_settings(
    user_id: int,
    user_privacy_settings_data: users_privacy_settings_schema.UsersPrivacySettingsUpdate,
    db: Session,
) -> users_privacy_settings_models.UsersPrivacySettings:
    """
    Update privacy settings for a specific user.

    Args:
        user_id: The ID of the user to update settings for.
        user_privacy_settings_data: Schema with fields to update.
        db: SQLAlchemy database session.

    Returns:
        The updated UsersPrivacySettings model.

    Raises:
        HTTPException: 404 error if settings not found.
        HTTPException: 500 error if database operation fails.
    """
    try:
        # Get the user privacy settings by the user id
        db_user_privacy_settings = get_user_privacy_settings_by_user_id(user_id, db)

        if db_user_privacy_settings is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User privacy settings not found",
            )

        # Dictionary of the fields to update if they are not None
        privacy_settings_dict = user_privacy_settings_data.model_dump(
            exclude_unset=True
        )
        # Iterate over the fields and update dynamically
        for key, value in privacy_settings_dict.items():
            setattr(db_user_privacy_settings, key, value)

        # Commit the transaction
        db.commit()
        db.refresh(db_user_privacy_settings)

        # Return the updated user privacy settings
        return db_user_privacy_settings
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in edit_user_privacy_settings: " f"{db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err
