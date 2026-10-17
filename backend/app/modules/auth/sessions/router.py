"""User session API endpoints."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Security,
    status,
)
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import modules.auth.dependencies as auth_dependencies
import modules.auth.sessions.crud as auth_sessions_crud
import modules.auth.sessions.schema as auth_sessions_schema

logger = core_logger.get_logger(__name__)

# Define the API router
router = APIRouter()


@router.get(
    "/user/{user_id}",
    response_model=list[auth_sessions_schema.UsersSessionsRead],
    status_code=status.HTTP_200_OK,
)
async def read_sessions_user(
    user_id: int,
    _check_scope: Annotated[
        None,
        Security(auth_dependencies.check_scopes, scopes=["sessions:read"]),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[auth_sessions_schema.UsersSessionsRead]:
    """
    Retrieve all sessions associated with a specific user.

    Args:
        user_id: The ID of the user whose sessions to retrieve.
        _check_scope: Scope validation dependency.
        db: Database session dependency.

    Returns:
        List of session objects for the specified user.
    """
    if core_config.settings.ENVIRONMENT != "demo":
        return auth_sessions_crud.get_user_sessions(user_id, db)
    else:
        logger.info("Session retrieval in demo environment - returning empty")
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
        Security(auth_dependencies.check_scopes, scopes=["sessions:write"]),
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
    auth_sessions_crud.delete_session(session_id, user_id, db)


@router.delete(
    "/user/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_sessions_user(
    user_id: int,
    _check_scope: Annotated[
        None,
        Security(auth_dependencies.check_scopes, scopes=["sessions:write"]),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    exclude_session_id: Annotated[
        str | None,
        Query(description="Session to keep intact (e.g. the caller's current session)"),
    ] = None,
) -> None:
    """
    Delete every session for a user, optionally keeping one intact.

    Backs the "revoke other sessions" action: pass the caller's current
    ``exclude_session_id`` to sign out every other device while staying
    logged in, or omit it (an admin acting on another user) to revoke
    all of that user's sessions.

    Args:
        user_id: The ID of the user whose sessions to revoke.
        _check_scope: Scope validation dependency.
        db: Database session dependency.
        exclude_session_id: Optional session to leave intact.

    Returns:
        None.
    """
    auth_sessions_crud.delete_sessions_by_user(
        user_id,
        db,
        exclude_session_id=exclude_session_id,
    )
