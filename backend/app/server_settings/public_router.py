from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

import server_settings.schema as server_settings_schema
import server_settings.utils as server_settings_utils

import core.database as core_database
import core.rate_limit as core_rate_limit

# Define the API router
router = APIRouter()


@router.get("", response_model=server_settings_schema.ServerSettingsReadPublic)
@core_rate_limit.limiter.limit(core_rate_limit.API_READ_LIMIT)
async def read_public_server_settings(
    request: Request,
    response: Response,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Get public server settings (unauthenticated).

    Protection Mechanisms:
    - Rate limiting: 60 requests per minute per IP (prevents DoS attacks)

    Returns only the public subset of server configuration
    (sensitive signup approval/verification settings excluded).
    Pydantic model filtering automatically excludes sensitive fields.

    Returns:
        Public subset of server configuration.
    """
    server_settings = server_settings_utils.get_server_settings(db)
    # Pydantic model_validate handles field filtering automatically
    return server_settings


@router.get(
    "/tile_maps_templates",
    response_model=list[server_settings_schema.TileMapsTemplate],
)
@core_rate_limit.limiter.limit(core_rate_limit.API_READ_LIMIT)
async def list_tile_maps_templates(
    request: Request,
    response: Response,
):
    """
    Retrieve available tile map templates for server settings (unauthenticated).

    Protection Mechanisms:
    - Rate limiting: 60 requests per minute per IP (prevents DoS attacks)

    This endpoint returns a list of all available tile map templates that can be
    used for configuring map display options in server settings.

    Returns:
        List of tile map template configurations available for the server.
    """
    return server_settings_utils.get_tile_maps_templates()
