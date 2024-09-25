import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, UploadFile, Security, HTTPException, status
from sqlalchemy.orm import Session

import health_data.schema as health_data_schema
import health_data.crud as health_data_crud

import session.security as session_security

import database
import dependencies_global

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get(
    "/number",
    response_model=int,
)
async def read_health_data_number(
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
    # Get the health_data number from the database
    return health_data_crud.get_health_data_number(token_user_id, db)


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=list[health_data_schema.HealthData] | None,
)
async def read_health_data_all_pagination(
    page_number: int,
    num_records: int,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["health:read"])
    ],
    validate_pagination_values: Annotated[
        Callable, Depends(dependencies_global.validate_pagination_values)
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
    # Get the health_data from the database with pagination
    return health_data_crud.get_health_data_with_pagination(
        token_user_id, db, page_number, num_records
    )


@router.post("/", response_model=health_data_schema.HealthData, status_code=201)
async def create_health_data(
    health_data: health_data_schema.HealthData,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["health:write"])
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
    # Creates the health_data in the database and returns it
    return health_data_crud.create_health_data(health_data, token_user_id, db)


@router.post("/weight", response_model=health_data_schema.HealthData, status_code=201)
async def create_health_weight_data(
    health_data: health_data_schema.HealthData,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["health:write"])
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
    health_for_date = health_data_crud.get_health_data_by_created_at(token_user_id, health_data.created_at, db)
    if health_for_date:
        # Edits the health_data in the database and returns it
        return health_data_crud.edit_health_weight_data(health_data, db)
    else:
        # Creates the health_data in the database and returns it
        return health_data_crud.create_health_weight_data(health_data, token_user_id, db)