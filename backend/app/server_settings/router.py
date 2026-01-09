import os
import aiofiles.os
from typing import Annotated, Callable

import aiofiles
from fastapi import (
    APIRouter,
    Depends,
    Security,
    UploadFile,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from safeuploads import FileValidator
from safeuploads.exceptions import FileValidationError

import server_settings.schema as server_settings_schema
import server_settings.crud as server_settings_crud
import server_settings.utils as server_settings_utils

import auth.security as auth_security

import core.database as core_database
import core.logger as core_logger
import core.config as core_config

# Define the API router
router = APIRouter()

# Initialize the file validator
file_validator = FileValidator()


@router.get(
    "",
    response_model=server_settings_schema.ServerSettingsRead,
    status_code=status.HTTP_200_OK,
)
async def read_server_settings(
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["server_settings:read"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> server_settings_schema.ServerSettingsRead:
    """
    Get current server settings.

    Requires admin authentication with server_settings:read scope.

    Returns:
        Current server settings configuration.
    """
    return server_settings_utils.get_server_settings(db)


@router.get(
    "/tile_maps_templates",
    response_model=list[server_settings_schema.TileMapsTemplate],
    status_code=status.HTTP_200_OK,
)
async def list_tile_maps_templates(
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["server_settings:read"]),
    ],
) -> list[server_settings_schema.TileMapsTemplate]:
    """
    Retrieve available tile map templates for server settings.

    This endpoint returns a list of all available tile map templates that can
    be used for configuring map display options in server settings.

    Returns:
        List of tile map template configurations available for the server.

    Raises:
        HTTPException: If the user lacks the required 'server_settings:read'
        scope.
    """
    return server_settings_utils.get_tile_maps_templates()


@router.put(
    "",
    response_model=server_settings_schema.ServerSettingsRead,
    status_code=status.HTTP_201_CREATED,
)
async def edit_server_settings(
    server_settings_attributes: server_settings_schema.ServerSettingsEdit,
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["server_settings:write"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> server_settings_schema.ServerSettingsRead:
    """
    Update server settings.

    Requires admin authentication with server_settings:write scope.

    Args:
        server_settings_attributes: Settings to update.

    Returns:
        Updated server settings configuration.
    """
    return server_settings_crud.edit_server_settings(server_settings_attributes, db)


@router.post(
    "/upload/login",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def upload_login_photo(
    file: UploadFile,
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["server_settings:write"]),
    ],
) -> dict:
    """
    Upload custom login page photo with security validation.

    Requires admin authentication with server_settings:write scope.

    Security measures:
    - SafeUploads validates file type via magic number (not extension)
    - File size limit enforced (max configured image size)
    - Filename hardcoded to 'login.png' (path traversal prevention)
    - Uploaded to isolated directory (core_config.SERVER_IMAGES_DIR)

    Args:
        file: Image file to upload.

    Returns:
        Success confirmation message.

    Raises:
        HTTPException: If file validation or upload fails.
    """
    try:
        await file_validator.validate_image_file(file)
        # Ensure the 'server_images' directory exists
        upload_dir = core_config.SERVER_IMAGES_DIR
        await aiofiles.os.makedirs(upload_dir, exist_ok=True)

        # Build the full path with the name "login.png"
        file_path = os.path.join(upload_dir, "login.png")

        # Save the uploaded file with the name "login.png"
        content = await file.read()
        async with aiofiles.open(file_path, "wb") as save_file:
            await save_file.write(content)

        return {"detail": "Login photo uploaded successfully"}
    except FileValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in upload_login_photo: {err}", "error", exc=err
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload login photo",
        ) from err


@router.delete(
    "/upload/login",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_login_photo(
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["server_settings:write"]),
    ],
) -> None:
    """
    Delete custom login page photo.

    Requires admin authentication with server_settings:write scope.

    Returns:
        Success confirmation message.

    Raises:
        HTTPException: If deletion fails.
    """
    try:
        # Build the full path to the file
        file_path = os.path.join(
            core_config.SERVER_IMAGES_DIR,
            "login.png",
        )

        # Check if the file exists and delete it asynchronously
        if await aiofiles.os.path.exists(file_path):
            await aiofiles.os.remove(file_path)
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in delete_login_photo: {err}", "error", exc=err
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete login photo",
        ) from err
