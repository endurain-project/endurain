"""Unauthenticated routes exposing the public subset of server settings."""

import hashlib
from typing import Annotated

import jasil.providers as platform_providers
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service

# Define the API router
router = APIRouter()


@router.get("", response_model=server_settings_schema.ServerSettingsReadPublic)
def read_public_server_settings(
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> server_settings_schema.ServerSettingsReadPublic:
    """Get public server settings (unauthenticated).

    Protection Mechanisms:
    - Rate limiting: the application's default per-IP limit applies.

    Returns only the public subset of server configuration
    (sensitive signup approval/verification settings excluded).
    Pydantic model filtering automatically excludes sensitive fields.

    Returns:
        Public subset of server configuration.
    """
    return server_settings_service.get_server_settings_for_public(db)


@router.get(
    "/tile_maps_templates",
    response_model=list[server_settings_schema.TileMapsTemplate],
)
def list_tile_maps_templates() -> list[server_settings_schema.TileMapsTemplate]:
    """Retrieve available tile map templates for server settings (unauthenticated).

    Protection Mechanisms:
    - Rate limiting: the application's default per-IP limit applies.

    This endpoint returns a list of all available tile map templates that can be
    used for configuring map display options in server settings.

    Returns:
        List of tile map template configurations available for the server.
    """
    return server_settings_service.get_tile_maps_templates()


# Browser cache for the login photo, in seconds; the ETag lets it revalidate cheaply after that.
_LOGIN_PHOTO_CACHE_MAX_AGE = 300


@router.get(
    "/login_photo",
    responses={200: {"content": {"image/*": {}}}, 304: {"description": "Not modified"}},
)
def read_login_photo(
    request: Request,
    storage: Annotated[
        platform_providers.StorageProvider,
        Depends(core_dependencies.get_storage),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> Response:
    """Serve the custom login page photo (unauthenticated).

    The login screen renders before anyone is signed in, so the photo is public by
    design; it is one admin-chosen image, not user data. The response carries an
    ETag, so a client that already holds the photo gets a 304 without the body.

    Args:
        request: The HTTP request, for its ``If-None-Match`` header.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The image bytes, or a 304 when the client's copy is current.

    Raises:
        NotFoundError: 404 when no custom photo is stored.
    """
    photo = server_settings_service.read_login_photo(storage, db)
    if photo is None:
        raise core_exceptions.NotFoundError("Login photo not found")
    data, media_type = photo
    etag = f'"{hashlib.sha256(data).hexdigest()[:32]}"'
    headers = {"Cache-Control": f"public, max-age={_LOGIN_PHOTO_CACHE_MAX_AGE}", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=data, media_type=media_type, headers=headers)
