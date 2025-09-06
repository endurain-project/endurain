import os
import glob
import secrets

from fastapi import HTTPException, status, UploadFile
from sqlalchemy.orm import Session

import shutil

import session.constants as session_constants

import users.user.crud as users_crud
import users.user.schema as users_schema

import core.logger as core_logger
import core.config as core_config


def check_user_is_active(user: users_schema.User) -> None:
    """
    Checks if the given user is active.

    Raises:
        HTTPException: If the user is not active, raises an HTTP 403 Forbidden exception
        with a detail message "Inactive user" and a "WWW-Authenticate" header.

    Args:
        user (users_schema.User): The user object to check.
    """
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )


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

        return users_crud.edit_user_photo_path(user_id, url_path_to_save, db)
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
