import logging
from typing import Annotated, Callable
from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import session.security as session_security

import garmin.utils as garmin_utils
import garmin.schema as garmin_schema

import database

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.put(
    "/link",
)
async def garminconnect_link(
    garmin_user: garmin_schema.GarminLogin,
    validate_access_token: Annotated[
        Callable,
        Depends(session_security.validate_access_token),
    ],
    check_scopes: Annotated[
        Callable,
        Security(session_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(database.get_db)],
):
    print("antes de chamar função")
    print(garmin_user)

    # Link Garmin Connect account
    garmin_utils.link_garminconnect(
        token_user_id, garmin_user.username, garmin_user.password, db
    )

    # Return success message
    return {f"Garmin Connect linked for user {token_user_id} successfully"}
