from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session

import session.security as session_security

import notifications.schema as notifications_schema
import notifications.crud as notifications_crud

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=list[notifications_schema.Notification] | None,
)
async def read_gear_user_pagination(
    page_number: int,
    num_records: int,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["profile:read"])
    ],
    token_user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return the notifications
    return notifications_crud.get_users_notifications_with_pagination(
        token_user_id, db, page_number, num_records
    )
