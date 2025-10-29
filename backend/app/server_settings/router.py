import os
from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security, UploadFile
from sqlalchemy.orm import Session

import server_settings.schema as server_settings_schema
import server_settings.crud as server_settings_crud
import server_settings.utils as server_settings_utils

import auth.security as auth_security

import core.database as core_database
import core.logger as core_logger
import core.config as core_config

# Define the API router
router = APIRouter()


@router.get("", response_model=server_settings_schema.ServerSettingsRead)
async def read_server_settings(
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["server_settings:read"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the server_settings from the database
    return server_settings_utils.get_server_settings(db)


@router.put("", response_model=server_settings_schema.ServerSettingsRead)
async def edit_server_settings(
    server_settings_attributtes: server_settings_schema.ServerSettingsEdit,
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["server_settings:write"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Update the server_settings in the database
    return server_settings_crud.edit_server_settings(server_settings_attributtes, db)


@router.post(
    "/upload/login",
    status_code=201,
)
async def upload_login_photo(
    file: UploadFile,
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["server_settings:write"]),
    ],
):
    try:
        # Ensure the 'server_images' directory exists
        upload_dir = core_config.SERVER_IMAGES_DIR
        os.makedirs(upload_dir, exist_ok=True)

        # Build the full path with the name "login.png"
        file_path = os.path.join(upload_dir, "login.png")

        # Save the uploaded file with the name "login.png"
        with open(file_path, "wb") as save_file:
            save_file.write(file.file.read())
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in upload_login_photo: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise err


@router.delete(
    "/upload/login",
    status_code=200,
)
async def delete_login_photo(
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["server_settings:write"]),
    ],
):
    try:
        # Build the full path to the file
        file_path = os.path.join(core_config.SERVER_IMAGES_DIR, "login.png")

        # Check if the file exists
        if os.path.exists(file_path):
            # Delete the file
            os.remove(file_path)
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in delete_login_photo: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise err
