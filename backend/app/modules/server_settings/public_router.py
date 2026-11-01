"""Unauthenticated routes exposing the public subset of server settings."""

from fastapi import APIRouter, Request, Response, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.rate_limit as core_rate_limit
import modules.server_settings.login_photo_service as server_settings_login_photo_service
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service
import modules.server_settings.tile_service as server_settings_tile_service

# Define the API router
router = APIRouter()


@router.get("", response_model=server_settings_schema.ServerSettingsReadPublic)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def read_public_server_settings(
    request: Request,
    db: core_dependencies.DbSession,
) -> server_settings_schema.ServerSettingsReadPublic:
    """Get public server settings (unauthenticated).

    Protection Mechanisms:
    - Rate limiting: the PUBLIC_READ per-IP limit applies.

    Returns only the public subset of server configuration
    (sensitive signup approval/verification settings excluded).
    Pydantic model filtering automatically excludes sensitive fields.

    Returns:
        Public subset of server configuration.
    """
    return server_settings_service.get_server_settings_for_public(db)


@router.get(
    "/tile-maps-templates",
    response_model=list[server_settings_schema.TileMapsTemplate],
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def list_tile_maps_templates(request: Request) -> list[server_settings_schema.TileMapsTemplate]:
    """Retrieve available tile map templates for server settings (unauthenticated).

    Protection Mechanisms:
    - Rate limiting: the PUBLIC_READ per-IP limit applies.

    This endpoint returns a list of all available tile map templates that can be
    used for configuring map display options in server settings.

    Returns:
        List of tile map template configurations available for the server.
    """
    return server_settings_tile_service.get_tile_maps_templates()


# Browser cache for the login photo, in seconds; the ETag lets it revalidate cheaply after that.
_LOGIN_PHOTO_CACHE_MAX_AGE = 300


@router.get(
    "/login-photo",
    responses={200: {"content": {"image/*": {}}}, 304: {"description": "Not modified"}},
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def read_login_photo(
    request: Request,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> Response:
    """Serve the custom login page photo (unauthenticated).

    The login screen renders before anyone is signed in, so the photo is public by
    design; it is one admin-chosen image, not user data. The response carries an
    ETag derived from the settings version, so a client that already holds the photo
    gets a 304 without storage being read.

    Args:
        request: The HTTP request, for its ``If-None-Match`` header.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The image bytes, or a 304 when the client's copy is current.

    Raises:
        NotFoundError: 404 when no custom photo is stored.
    """
    version = server_settings_login_photo_service.get_login_photo_version(db)
    if version is None:
        raise core_exceptions.NotFoundError("Login photo not found")
    etag = core_etag.format_etag(version)
    headers = {"Cache-Control": f"public, max-age={_LOGIN_PHOTO_CACHE_MAX_AGE}", "ETag": etag}
    # Answered from the settings row alone: a client that holds the photo costs no storage read.
    if core_etag.matches_if_none_match(request.headers.get("if-none-match"), version):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    photo = server_settings_login_photo_service.read_login_photo(storage)
    if photo is None:
        raise core_exceptions.NotFoundError("Login photo not found")
    data, media_type = photo
    return Response(content=data, media_type=media_type, headers=headers)
