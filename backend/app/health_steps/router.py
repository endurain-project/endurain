from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
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


@router.post("", status_code=201)
async def create_health_steps(
    health_steps: health_steps_schema.HealthSteps,
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
    # Check if health_steps for this date already exists
    steps_for_date = health_steps_crud.get_health_steps_by_date(
        token_user_id, health_steps.date, db
    )

    if steps_for_date:
        health_steps.id = steps_for_date.id
        # Updates the health_steps in the database and returns it
        return health_steps_crud.edit_health_steps(token_user_id, health_steps, db)
    else:
        # Creates the health_steps in the database and returns it
        return health_steps_crud.create_health_steps(token_user_id, health_steps, db)


@router.put("")
async def edit_health_steps(
    health_steps: health_steps_schema.HealthSteps,
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
    # Updates the health_steps in the database and returns it
    return health_steps_crud.edit_health_steps(token_user_id, health_steps, db)


@router.delete("/{health_steps_id}")
async def delete_health_steps(
    health_steps_id: int,
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
    # Deletes entry from database
    return health_steps_crud.delete_health_steps(token_user_id, health_steps_id, db)
