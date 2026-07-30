import asyncio
from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Security,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.dependencies as auth_dependencies
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.utils as server_settings_utils

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=server_settings_schema.ServerSettingsRead,
    status_code=status.HTTP_200_OK,
)
def read_server_settings(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:read"]),
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
        Current server settings configuration with decrypted API key.
    """
    return server_settings_utils.get_server_settings_for_admin(db)


@router.get(
    "/tile_maps_templates",
    response_model=list[server_settings_schema.TileMapsTemplate],
    status_code=status.HTTP_200_OK,
)
def list_tile_maps_templates(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:read"]),
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
    status_code=status.HTTP_200_OK,
)
def edit_server_settings(
    request: Request,
    server_settings_attributes: server_settings_schema.ServerSettingsEdit,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
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
        request: FastAPI request object for accessing app state.
        server_settings_attributes: Settings to update.

    Returns:
        Updated server settings configuration.
    """
    server_settings_updated = server_settings_crud.edit_server_settings(server_settings_attributes, db)

    # Update allowed tile domains in app.state if tileserver_url changed
    if server_settings_attributes.tileserver_url is not None:
        try:
            request.app.state.allowed_tile_domains = server_settings_utils.get_allowed_tile_domains(db)
            core_logger.print_to_log(f"Updated allowed tile domains: {request.app.state.allowed_tile_domains}")
        except Exception as e:
            core_logger.print_to_log(f"Error updating tile domains in app.state: {e}", "error", exc=e)

    # Trigger full thumbnail regeneration if the setting is enabled
    # and any map-related field was part of this update
    _map_fields = {"tileserver_url", "tileserver_api_key", "map_background_color"}
    changed_fields = set(server_settings_attributes.model_dump(exclude_unset=True).keys())
    if server_settings_updated.tileserver_regenerate_thumbnails_on_change and (changed_fields & _map_fields):
        core_logger.print_to_log(
            "Tile server settings changed with regeneration enabled — scheduling thumbnail regeneration",
            "info",
        )
        core_scheduler.schedule_thumbnail_regeneration()

    return server_settings_updated


@router.post(
    "/upload/login",
    response_model=dict[str, str],
    status_code=status.HTTP_201_CREATED,
)
async def upload_login_photo(
    file: UploadFile,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> dict[str, str]:
    """
    Upload custom login page photo.

    Requires admin authentication with server_settings:write scope.

    Args:
        file: Image file to upload.

    Returns:
        Full file path where file was saved.
    """
    # Save file using centralized file upload handler
    await core_file_uploads.save_validated_upload(
        file,
        kind=core_file_uploads.UploadKind.IMAGE,
        upload_dir=core_config.SERVER_IMAGES_DIR,
        filename="login.png",
    )

    await asyncio.to_thread(server_settings_crud.update_server_settings_login_photo_set, True, db)

    return {"message": "Login photo uploaded successfully."}


@router.delete(
    "/upload/login",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_login_photo(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
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
    await core_file_uploads.delete_files_by_pattern(core_config.SERVER_IMAGES_DIR, "login.png")

    await asyncio.to_thread(server_settings_crud.update_server_settings_login_photo_set, False, db)
