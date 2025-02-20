from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import server_settings.schema as server_settings_schema
import server_settings.crud as server_settings_crud

import session.security as session_security

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get("", response_model=server_settings_schema.ServerSettings)
async def read_server_settings(
    check_scopes: Annotated[
        Callable,
        Security(session_security.check_scopes, scopes=["server_settings:read"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the server_settings from the database
    return server_settings_crud.get_server_settings(db)


@router.put("", response_model=server_settings_schema.ServerSettings)
async def edit_server_settings(
    server_settings_attributtes: server_settings_schema.ServerSettings,
    check_scopes: Annotated[
        Callable,
        Security(session_security.check_scopes, scopes=["server_settings:write"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Update the server_settings in the database
    return server_settings_crud.edit_server_settings(server_settings_attributtes, db)
