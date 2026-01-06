from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import server_settings.schema as server_settings_schema
import server_settings.utils as server_settings_utils

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get("", response_model=server_settings_schema.ServerSettingsReadPublic)
async def read_public_server_settings(
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Get public server settings (unauthenticated).

    Returns only the public subset of server configuration
    (sensitive signup approval/verification settings excluded).
    Pydantic model filtering automatically excludes sensitive fields.

    Returns:
        Public subset of server configuration.
    """
    server_settings = server_settings_utils.get_server_settings(db)
    # Pydantic model_validate handles field filtering automatically
    return server_settings
