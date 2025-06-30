from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import health_targets.schema as health_targets_schema
import health_targets.crud as health_targets_crud

import session.security as session_security

import core.database as core_database

# Define the API router
router = APIRouter()


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
        Depends(core_database.get_db),
    ],
):
    # Get the health_targets from the database
    return health_targets_crud.get_health_targets_by_user_id(token_user_id, db)
