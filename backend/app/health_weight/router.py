import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, UploadFile, Security, HTTPException, status
from sqlalchemy.orm import Session

import health_weight.schema as health_weight_schema
import health_weight.crud as health_weight_crud

import auth.security as auth_security

import core.database as core_database
import core.dependencies as core_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/number",
    response_model=int,
)
async def read_health_weight_number(
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
    # Get the health_weight number from the database
    return health_weight_crud.get_health_weight_number(token_user_id, db)


@router.get(
    "",
    response_model=list[health_weight_schema.HealthWeight] | None,
)
async def read_health_weight_all(
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
    # Get the health_weight from the database
    return health_weight_crud.get_all_health_weight_by_user_id(token_user_id, db)


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=list[health_weight_schema.HealthWeight] | None,
)
async def read_health_weight_all_pagination(
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
    # Get the health_weight from the database with pagination
    return health_weight_crud.get_health_weight_with_pagination(
        token_user_id, db, page_number, num_records
    )


@router.post("", status_code=201)
async def create_health_weight(
    health_weight: health_weight_schema.HealthWeight,
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
    # Check if health_weight for this date already exists
    health_for_date = health_weight_crud.get_health_weight_by_date(
        token_user_id, health_weight.date, db
    )

    if health_for_date:
        health_weight.id = health_for_date.id
        # Updates the health_weight in the database and returns it
        return health_weight_crud.edit_health_weight(token_user_id, health_weight, db)
    else:
        # Creates the health_weight in the database and returns it
        return health_weight_crud.create_health_weight(token_user_id, health_weight, db)


@router.put("")
async def edit_health_weight(
    health_weight: health_weight_schema.HealthWeight,
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
    # Updates the health_weight in the database and returns it
    return health_weight_crud.edit_health_weight(token_user_id, health_weight, db)


@router.delete("/{health_weight_id}")
async def delete_health_weight(
    health_weight_id: int,
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
    return health_weight_crud.delete_health_weight(token_user_id, health_weight_id, db)
