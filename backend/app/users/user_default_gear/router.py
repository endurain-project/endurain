from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import users.user_default_gear.schema as user_default_gear_schema
import users.user_default_gear.crud as user_default_gear_crud

import auth.security as auth_security

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get("", response_model=user_default_gear_schema.UserDefaultGear)
async def read_user_default_gear(
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the user default gear from the database
    return user_default_gear_crud.get_user_default_gear_by_user_id(token_user_id, db)


@router.put("", response_model=user_default_gear_schema.UserDefaultGear)
async def edit_user_default_gear(
    user_default_gear: user_default_gear_schema.UserDefaultGear,
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Update the user default gear in the database
    return user_default_gear_crud.edit_user_default_gear(
        user_default_gear, token_user_id, db
    )
