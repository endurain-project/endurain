from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import server_settings.schema as server_settings_schema
import server_settings.crud as server_settings_crud

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
    # Get the server_settings from the database
    server_settings = server_settings_crud.get_server_settings(db)

    delattr(server_settings, "signup_require_admin_approval")
    delattr(server_settings, "signup_require_email_verification")

    return server_settings
