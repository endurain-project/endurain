import os
import glob

from fastapi import HTTPException, status, UploadFile
from sqlalchemy.orm import Session

import shutil

import auth.password_hasher as auth_password_hasher

import users.user.crud as users_crud
import users.user.schema as users_schema
import users.user.models as users_models

import users.user_integrations.crud as user_integrations_crud
import users.user_default_gear.crud as user_default_gear_crud
import users.user_privacy_settings.crud as users_privacy_settings_crud
import health.health_targets.crud as health_targets_crud
import server_settings.models as server_settings_models
import server_settings.schema as server_settings_schema

import core.logger as core_logger
import core.config as core_config


def get_user_by_id_or_404(user_id: int, db: Session) -> users_models.User:
    """
    Retrieve user by ID or raise 404 error.

    Args:
        user_id: User ID to search for.
        db: SQLAlchemy database session.

    Returns:
        User model (guaranteed non-None).

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


def create_user_default_data(user_id: int, db: Session) -> None:
    # Create the user integrations in the database
    user_integrations_crud.create_user_integrations(user_id, db)

    # Create the user privacy settings
    users_privacy_settings_crud.create_user_privacy_settings(user_id, db)

    # Create the user health targets
    health_targets_crud.create_health_targets(user_id, db)

    # Create the user default gear
    user_default_gear_crud.create_user_default_gear(user_id, db)


def check_password_and_hash(
    password: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    server_settings: (
        server_settings_models.ServerSettings
        | server_settings_schema.ServerSettingsRead
    ),
    user_access_type: int,
) -> str:
    """
    Validates password against the configured policy and hashes it.

    Args:
        password (str): The password to validate and hash.
        password_hasher (PasswordHasher): The password hasher instance.
        server_settings (ServerSettings | ServerSettingsRead): The server settings containing password policies.
        user_access_type (int): The access type of the user (e.g., 1 for regular, 2 for admin).

    Returns:
        str: The hashed password.

    Raises:
        HTTPException: If password validation fails.
    """
    # Determine minimum length based on user access type
    min_length = (
        server_settings.password_length_admin_users
        if user_access_type == 2
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


def check_user_is_active(user: users_schema.UserRead) -> None:
    """
    Checks if the given user is active.

    Raises:
        HTTPException: If the user is not active, raises an HTTP 403 Forbidden exception
        with a detail message "Inactive user" and a "WWW-Authenticate" header.

    Args:
        user (users_schema.UserRead): The user object to check.
    """
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_admin_users(db: Session):
    admins = users_crud.get_users_admin(db)

    if not admins:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No admin users found",
        )

    return admins


def delete_user_photo_filesystem(user_id: int):
    """
    Deletes all photo files associated with a user from the filesystem.

    This function searches for files in the directory specified by `core_config.USER_IMAGES_DIR`
    that match the given `user_id` with any file extension, and removes them.

    Args:
        user_id (int): The ID of the user whose photo files should be deleted.

    Returns:
        None
    """
    # Define the pattern to match files with the specified name regardless of the extension
    folder = core_config.USER_IMAGES_DIR
    file = f"{user_id}.*"

    # Find all files matching the pattern
    files_to_delete = glob.glob(os.path.join(folder, file))

    # Remove each file found
    for file_path in files_to_delete:
        if os.path.exists(file_path):
            os.remove(file_path)


def format_user_birthdate(user):
    """
    Formats the birthdate attribute of a user object to an ISO 8601 string if it is a date/datetime object.
    If the birthdate is already a string or None, it remains unchanged.

    Args:
        user: An object with a 'birthdate' attribute, which can be a string, date/datetime object, or None.

    Returns:
        The user object with the 'birthdate' attribute formatted as an ISO 8601 string, string, or None.
    """
    user.birthdate = (
        user.birthdate
        if isinstance(user.birthdate, str)
        else user.birthdate.isoformat() if user.birthdate else None
    )
    return user


async def save_user_image(user_id: int, file: UploadFile, db: Session):
    """
    Saves a user's image to the server and updates the user's photo path in the database.

    Args:
        user_id (int): The ID of the user whose image is being saved.
        file (UploadFile): The uploaded image file.
        db (Session): The database session.

    Returns:
        Any: The result of updating the user's photo path in the database.

    Raises:
        HTTPException: If an error occurs during the image saving process, raises a 500 Internal Server Error.
    """
    try:
        upload_dir = core_config.USER_IMAGES_DIR
        os.makedirs(upload_dir, exist_ok=True)

        # Get file extension
        _, file_extension = os.path.splitext(file.filename)
        filename = f"{user_id}{file_extension}"

        file_path_to_save = os.path.join(upload_dir, filename)
        url_path_to_save = os.path.join(core_config.USER_IMAGES_DIR, filename)

        with open(file_path_to_save, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return users_crud.update_user_photo(user_id, db, url_path_to_save)
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in save_user_image: {err}", "error", exc=err)

        # Remove the file after processing
        if os.path.exists(file_path_to_save):
            os.remove(file_path_to_save)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
