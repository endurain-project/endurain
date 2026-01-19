import os

from fastapi import HTTPException, status, UploadFile
from sqlalchemy.orm import Session

import auth.password_hasher as auth_password_hasher

import users.users.crud as users_crud
import users.users.schema as users_schema
import users.users.models as users_models

import users.users_integrations.crud as user_integrations_crud
import users.users_default_gear.crud as user_default_gear_crud
import users.users_privacy_settings.crud as users_privacy_settings_crud
import health.health_targets.crud as health_targets_crud
import server_settings.models as server_settings_models
import server_settings.schema as server_settings_schema

import core.file_uploads as core_file_uploads
import core.config as core_config


def get_user_by_id_or_404(user_id: int, db: Session) -> users_models.Users:
    """
    Retrieve user by ID or raise 404 error.

    Args:
        user_id: User ID to search for.
        db: SQLAlchemy database session.

    Returns:
        Users model (guaranteed non-None).

    Raises:
        HTTPException: 404 if user not found.
    """
    # Get the user from the database
    db_user = users_crud.get_user_by_id(user_id, db)

    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return db_user


def get_admin_users_or_404(db: Session) -> list[users_models.Users]:
    """
    Retrieve all admin users from database or raise 404 error.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of all admin User models.

    Raises:
        HTTPException: 404 if no admin users found.
    """
    admins = users_crud.get_users_admin(db)

    if not admins:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No admin users found",
        )

    return admins


def check_password_and_hash(
    password: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    server_settings: (
        server_settings_models.ServerSettings
        | server_settings_schema.ServerSettingsRead
    ),
    user_access_type: str,
) -> str:
    """
    Validates password against the configured policy and hashes it.

    Args:
        password (str): The password to validate and hash.
        password_hasher (PasswordHasher): The password hasher instance.
        server_settings (ServerSettings | ServerSettingsRead): The server settings containing password policies.
        user_access_type (str): The access type of the user (e.g., "regular" or "admin").

    Returns:
        str: The hashed password.

    Raises:
        HTTPException: If password validation fails.
    """
    # Determine minimum length based on user access type
    min_length = (
        server_settings.password_length_admin_users
        if user_access_type == users_schema.UserAccessType.ADMIN
        else server_settings.password_length_regular_users
    )
    # Check if password meets requirements
    try:
        password_hasher.validate_password(
            password, min_length, str(server_settings.password_type)
        )
    except auth_password_hasher.PasswordPolicyError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    # Hash the password
    hashed_password = password_hasher.hash_password(password)

    # Return the hashed password
    return hashed_password


def check_user_is_active(
    user: users_models.Users | users_schema.UsersRead,
) -> None:
    """
    Check if user is active and raise 403 if inactive.

    Args:
        user: User object to check (User or UsersRead schema).

    Returns:
        None

    Raises:
        HTTPException: 403 if user is not active.
    """
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_user_default_data(user_id: int, db: Session) -> None:
    """
    Create default data for newly created user.

    Args:
        user_id: ID of user to create default data for.
        db: SQLAlchemy database session.

    Returns:
        None
    """
    # Create the user integrations in the database
    user_integrations_crud.create_user_integrations(user_id, db)

    # Create the user privacy settings
    users_privacy_settings_crud.create_user_privacy_settings(user_id, db)

    # Create the user health targets
    health_targets_crud.create_health_targets(user_id, db)

    # Create the user default gear
    user_default_gear_crud.create_user_default_gear(user_id, db)


async def save_user_image_file(user_id: int, file: UploadFile, db: Session) -> str:
    """
    Save user image file with security validation and update DB.

    Uses centralized file upload handler for validation and async
    I/O, then updates user photo path in database.

    Args:
        user_id: ID of user whose image is being saved.
        file: Uploaded image file (UploadFile).
        db: SQLAlchemy database session.

    Returns:
        Path to saved image file.

    Raises:
        HTTPException: 400 if filename missing, 500 if upload
            fails.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Get file extension and build filename
    _, file_extension = os.path.splitext(file.filename)
    filename = f"{user_id}{file_extension}"

    # Save file using centralized file upload handler
    await core_file_uploads.save_image_file_and_validate_it(
        file, core_config.USER_IMAGES_DIR, filename
    )

    # Update user photo path in database
    return str(
        await users_crud.update_user_photo(
            user_id, db, os.path.join(core_config.USER_IMAGES_DIR, filename)
        )
    )


async def delete_user_photo_filesystem(user_id: int) -> None:
    """
    Delete user photo files from filesystem.

    Args:
        user_id: ID of user whose photo files to delete.

    Returns:
        None
    """
    await core_file_uploads.delete_files_by_pattern(
        core_config.USER_IMAGES_DIR, f"{user_id}.*"
    )
