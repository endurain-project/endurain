import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, UploadFile, Security, HTTPException, status
from sqlalchemy.orm import Session

import health_targets.schema as health_targets_schema
import health_targets.crud as health_targets_crud

import session.security as session_security

import database
import dependencies_global

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get(
    "/",
    response_model=health_targets_schema.HealthTargets | None,
)
async def read_health_data_all_pagination(
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["health:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Get the health_targets from the database
    return health_targets_crud.get_user_health_targets(
        token_user_id, db
    )
