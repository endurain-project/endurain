import asyncio
from collections.abc import Callable
from typing import Annotated

import jasil.providers as platform_providers
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
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service
import modules.server_settings.utils as server_settings_utils
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)

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
    server_settings_updated = server_settings_service.edit_server_settings(server_settings_attributes, db)

    # Update allowed tile domains in app.state if tileserver_url changed
    if server_settings_attributes.tileserver_url is not None:
        try:
            request.app.state.allowed_tile_domains = server_settings_utils.get_allowed_tile_domains(db)
            logger.info(f"Updated allowed tile domains: {request.app.state.allowed_tile_domains}")
        except Exception as e:
            logger.error(f"Error updating tile domains in app.state: {e}", exc_info=e)

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


@router.get(
    "/email",
    response_model=server_settings_schema.EmailStatus,
    status_code=status.HTTP_200_OK,
)
def read_email_status(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:read"]),
    ],
) -> server_settings_schema.EmailStatus:
    """
    Get whether outgoing email is usable.

    Requires admin authentication with server_settings:read scope.

    Returns:
        Whether email is configured and, when not, the reasons (setting names only).
    """
    return server_settings_service.get_email_status()


@router.post(
    "/email/test",
    response_model=dict[str, str],
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def send_test_email(
    request: Request,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
    ],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    mail: Annotated[
        platform_providers.MailProvider,
        Depends(core_dependencies.get_mail),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> dict[str, str]:
    """
    Send a test email to the requesting admin.

    Requires admin authentication with server_settings:write scope. The recipient
    is always the caller's own email address.

    Args:
        request: The HTTP request object.
        mail: The platform mail provider.

    Returns:
        A confirmation message naming the recipient address.

    Raises:
        ServiceUnavailableError: 503 if email is not configured.
        UpstreamError: 502 if the mail server did not accept the message.
    """
    admin = users_integration.get_user(token_user_id, db)
    if admin is None:
        raise core_exceptions.NotFoundError("User not found")
    server_settings_service.send_test_email(admin, mail)
    return {"message": f"Test email sent to {admin.email}."}
