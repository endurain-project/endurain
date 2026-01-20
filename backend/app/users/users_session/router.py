"""User session API endpoints."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Security,
    status,
)
from sqlalchemy.orm import Session

import auth.security as auth_security

import users.users_session.crud as users_session_crud
import users.users_session.schema as users_session_schema

import core.database as core_database
import core.logger as core_logger
import core.config as core_config

# Define the API router
router = APIRouter()


@router.get(
    "/user/{user_id}",
    response_model=list[users_session_schema.UsersSessionsRead],
    status_code=status.HTTP_200_OK,
)
async def read_sessions_user(
    user_id: int,
    _check_scope: Annotated[
        None,
        Security(auth_security.check_scopes, scopes=["sessions:read"]),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[users_session_schema.UsersSessionsRead]:
    """
    Retrieve all sessions associated with a specific user.

    Args:
        user_id: The ID of the user whose sessions to retrieve.
        _check_scope: Scope validation dependency.
        db: Database session dependency.

    Returns:
        List of session objects for the specified user.
    """
    if core_config.ENVIRONMENT != "demo":
        return users_session_crud.get_user_sessions(user_id, db)
    else:
        core_logger.print_to_log(
            "Session retrieval in demo environment - returning empty",
            "info",
        )
        return []


@router.delete(
    "/{session_id}/user/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_session_user(
    session_id: str,
    user_id: int,
    _check_scope: Annotated[
        None,
        Security(auth_security.check_scopes, scopes=["sessions:write"]),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> None:
    """
    Delete a user session.

    Args:
        session_id: The ID of the session to delete.
        user_id: The ID of the user who owns the session.
        _check_scope: Scope validation dependency.
        db: Database session dependency.

    Returns:
        None.

    Raises:
        HTTPException: If session not found or unauthorized.
    """
    users_session_crud.delete_session(session_id, user_id, db)
