import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, UploadFile, Security, HTTPException, status
from sqlalchemy.orm import Session

import health_steps.schema as health_steps_schema
import health_steps.crud as health_steps_crud

import auth.security as auth_security

import core.database as core_database
import core.dependencies as core_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/number",
    response_model=int,
)
async def read_health_steps_number(
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
    # Get the health_steps number from the database
    return health_steps_crud.get_health_steps_number(token_user_id, db)


@router.get(
    "",
    response_model=list[health_steps_schema.HealthSteps] | None,
)
async def read_health_steps_all(
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
    # Get the health_steps from the database
    return health_steps_crud.get_all_health_steps_by_user_id(token_user_id, db)


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=list[health_steps_schema.HealthSteps] | None,
)
async def read_health_steps_all_pagination(
    page_number: int,
    num_records: int,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["health:read"])
    ],
    validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
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
    # Get the health_steps from the database with pagination
    return health_steps_crud.get_health_steps_with_pagination(
        token_user_id, db, page_number, num_records
    )
