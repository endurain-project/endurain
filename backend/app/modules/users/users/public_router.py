"""Public user router for unauthenticated user info access."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

import core.database as core_database
import modules.users.users.crud as users_crud
import modules.users.users.dependencies as users_dependencies
import modules.users.users.schema as users_schema

# Define the API router
router = APIRouter()


@router.get(
    "/id/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=users_schema.UsersRead | None,
)
def read_users_id(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> users_schema.UsersRead | None:
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
