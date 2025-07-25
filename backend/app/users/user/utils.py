import os
import glob

from fastapi import HTTPException, status, UploadFile
from sqlalchemy.orm import Session

import shutil

import session.constants as session_constants

import users.user.crud as users_crud
import users.user.schema as users_schema

import core.logger as core_logger
import core.config as core_config


def check_user_is_active(user: users_schema.User) -> None:
    if user.is_active == session_constants.USER_NOT_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )


def delete_user_photo_filesystem(user_id: int):
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
    user.birthdate = user.birthdate if isinstance(user.birthdate, str) else user.birthdate.isoformat() if user.birthdate else None
    return user


async def save_user_image(user_id: int, file: UploadFile, db: Session):
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
