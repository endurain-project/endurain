from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import health_sleep.schema as health_sleep_schema
import health_sleep.crud as health_sleep_crud

import auth.security as auth_security

import core.database as core_database
import core.dependencies as core_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/number",
    response_model=int,
)
async def read_health_sleep_number(
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
    # Get the health_sleep number from the database
    return health_sleep_crud.get_health_sleep_number(token_user_id, db)


@router.get(
    "",
    response_model=list[health_sleep_schema.HealthSleep] | None,
)
async def read_health_sleep_all(
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
    # Get the health_sleep from the database
    return health_sleep_crud.get_all_health_sleep_by_user_id(token_user_id, db)


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=list[health_sleep_schema.HealthSleep] | None,
)
async def read_health_sleep_all_pagination(
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
    # Get the health_sleep from the database with pagination
    return health_sleep_crud.get_health_sleep_with_pagination(
        token_user_id, db, page_number, num_records
    )
