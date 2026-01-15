from typing import Annotated, Callable

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import users.user.schema as users_schema
import users.user.crud as users_crud
import users.user.dependencies as users_dependencies

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get("/id/{user_id}", response_model=users_schema.UserRead)
async def read_users_id(
    user_id: int,
    validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the users from the database by id
    return users_crud.get_user_by_id(user_id, db, public_check=True)
