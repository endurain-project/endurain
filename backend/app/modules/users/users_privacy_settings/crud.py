"""CRUD operations for user privacy settings."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.users.users_privacy_settings.models as users_privacy_settings_models
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema

# Private internal helpers


def _transform_users_privacy_settings(
    users: users_privacy_settings_models.UsersPrivacySettings,
) -> users_privacy_settings_schema.UsersPrivacySettingsRead:
    """
    Transform a user privacy settings instance to a Pydantic schema.

    Args:
        users: The user privacy settings ORM instance.

    Returns:
        The user privacy settings as a schema.
    """
    return users_privacy_settings_schema.UsersPrivacySettingsRead.model_validate(users)


@core_decorators.handle_db_errors
def _get_user_privacy_settings_model_by_user_id_or_404(
    user_id: int, db: Session
) -> users_privacy_settings_models.UsersPrivacySettings:
    """
    Retrieve privacy settings for a specific user.

    Args:
        user_id: The ID of the user to fetch privacy settings for.
        db: SQLAlchemy database session.

    Returns:
        The UsersPrivacySettings ORM model for the user.

    Raises:
        HTTPException: 404 error if privacy settings not found.
        HTTPException: 500 error if database query fails.
    """
    # Get the user privacy settings by the user id
    stmt = select(users_privacy_settings_models.UsersPrivacySettings).where(
        users_privacy_settings_models.UsersPrivacySettings.user_id == user_id
    )
    db_users_privacy_settings = db.execute(stmt).scalar_one_or_none()

    if not db_users_privacy_settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User privacy settings not found",
        )

    return db_users_privacy_settings


# Public CRUD functions


@core_decorators.handle_db_errors
def get_user_privacy_settings_by_user_id(
    user_id: int, db: Session
) -> users_privacy_settings_schema.UsersPrivacySettingsRead | None:
    """
    Retrieve privacy settings for a specific user.

    Args:
        user_id: The ID of the user to fetch settings for.
        db: SQLAlchemy database session.

    Returns:
        The UsersPrivacySettingsRead schema if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    # Get the user privacy settings by the user id
    stmt = select(users_privacy_settings_models.UsersPrivacySettings).where(
        users_privacy_settings_models.UsersPrivacySettings.user_id == user_id
    )
    db_users_privacy_settings = db.execute(stmt).scalar_one_or_none()
    return _transform_users_privacy_settings(db_users_privacy_settings) if db_users_privacy_settings else None


@core_decorators.handle_db_errors
def create_user_privacy_settings(user_id: int, db: Session) -> users_privacy_settings_schema.UsersPrivacySettingsRead:
    """
    Create privacy settings for a user.

    Args:
        user_id: The ID of the user to create settings for.
        db: SQLAlchemy database session.

    Returns:
        The created UsersPrivacySettingsRead schema.

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
        return _transform_users_privacy_settings(db_privacy_settings)
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Privacy settings already exist for this user",
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_user_privacy_settings(
    user_id: int,
    user_privacy_settings_data: users_privacy_settings_schema.UsersPrivacySettingsUpdate,
    db: Session,
) -> users_privacy_settings_schema.UsersPrivacySettingsRead:
    """
    Update privacy settings for a specific user.

    Args:
        user_id: The ID of the user to update settings for.
        user_privacy_settings_data: Schema with fields to update.
        db: SQLAlchemy database session.

    Returns:
        The updated UsersPrivacySettingsRead schema.

    Raises:
        HTTPException: 404 error if settings not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user privacy settings by the user id
    db_user_privacy_settings = _get_user_privacy_settings_model_by_user_id_or_404(user_id, db)

    # Dictionary of the fields to update if they are not None
    privacy_settings_dict = user_privacy_settings_data.model_dump(exclude_unset=True, exclude={"user_id", "id"})
    # Iterate over the fields and update dynamically
    for key, value in privacy_settings_dict.items():
        setattr(db_user_privacy_settings, key, value)

    # Commit the transaction
    db.commit()
    db.refresh(db_user_privacy_settings)

    # Return the updated user privacy settings
    return _transform_users_privacy_settings(db_user_privacy_settings)
