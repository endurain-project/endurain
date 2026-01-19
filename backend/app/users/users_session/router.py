from typing import Annotated, Callable

from fastapi import (
    APIRouter,
    Depends,
    Security,
)
from sqlalchemy.orm import Session

import auth.security as auth_security

import users.users_session.crud as users_session_crud

import core.database as core_database
import core.logger as core_logger
import core.config as core_config

# Define the API router
router = APIRouter()


@router.get("/user/{user_id}")
async def read_sessions_user(
    user_id: int,
    _check_scope: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["sessions:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Retrieve all sessions associated with a specific user.

    Args:
        user_id (int): The ID of the user whose sessions are to be retrieved.
        _validate_access_token (Callable): Dependency that validates the access token for authentication.
        __check_scope (Callable): Dependency that checks if the user has the required scope for reading sessions.
        db (Session): Database session dependency.

    Returns:
        List[Session]: A list of session objects associated with the specified user.
    """
    # Get the sessions from the database
    if core_config.ENVIRONMENT != "demo":
        return users_session_crud.get_user_sessions(user_id, db)
    else:
        core_logger.print_to_log(
            "Session retrieval attempted in demo environment - returning empty list",
            "info",
        )
        return []


@router.delete("/{session_id}/user/{user_id}")
async def delete_session_user(
    session_id: str,
    user_id: int,
    _check_scope: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["sessions:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Deletes a user from a session.

    Args:
        session_id (str): The ID of the session from which the user will be removed.
        user_id (int): The ID of the user to be removed from the session.
        _validate_access_token (Callable): Dependency that validates the access token.
        __check_scope (Callable): Dependency that checks if the user has the required scope ("sessions:write").
        db (Session): Database session dependency.

    Returns:
        Any: The result of the session deletion operation.

    Raises:
        HTTPException: If the session or user does not exist, or if access is unauthorized.
    """
    # Delete the session from the database
    return users_session_crud.delete_session(session_id, user_id, db)
