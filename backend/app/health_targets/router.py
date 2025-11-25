from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import health_targets.schema as health_targets_schema
import health_targets.crud as health_targets_crud

import auth.security as auth_security

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "/",
    response_model=health_targets_schema.HealthTargets | None,
)
async def read_health_targets_all_pagination(
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["health:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the health_targets from the database
    return health_targets_crud.get_health_targets_by_user_id(token_user_id, db)


@router.put(
    "/",
    response_model=None,
    status_code=204,
)
async def update_health_targets(
    health_targets: health_targets_schema.HealthTargets,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["health:write"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Update the health_targets in the database
    health_targets_crud.edit_health_target(health_targets, token_user_id, db)
