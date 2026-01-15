"""Public user router for unauthenticated user info access."""

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

import users.user.schema as users_schema
import users.user.crud as users_crud
import users.user.dependencies as users_dependencies

import core.database as core_database

# Define the API router
router = APIRouter()


@router.get(
    "/id/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=users_schema.UserRead | None,
)
async def read_users_id(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> users_schema.UserRead | None:
    """
    Get public user info by ID.

    Args:
        user_id: The user ID to retrieve.
        _validate_id: User ID validation dependency.
        db: Database session dependency.

    Returns:
        User data if found and public sharing enabled.
    """
    return users_crud.get_user_by_id(user_id, db, public_check=True)
