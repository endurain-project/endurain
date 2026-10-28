"""Admin API endpoints for auth sessions."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Security, status
from starlette.responses import Response

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.auth.sessions.schema as sessions_schema
import modules.auth.sessions.service as sessions_service

router = APIRouter()
UserId = Annotated[int, Path()]
SessionId = Annotated[str, Path()]


@router.get(
    "/user/{user_id}",
    response_model=list[sessions_schema.UsersSessionsRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["sessions:read"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_READ)
def read_sessions_user(
    request: Request,
    user_id: UserId,
    db: core_dependencies.DbSession,
) -> list[sessions_schema.UsersSessionsRead]:
    """Retrieve all sessions associated with a specific user.

    Args:
        user_id: The ID of the user whose sessions to retrieve.
        _check_scope: Scope validation dependency.
        db: Database session dependency.

    Returns:
        List of session objects for the specified user.
    """
    return sessions_service.get_user_sessions(user_id, db)


@router.delete(
    "/{session_id}/user/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["sessions:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_session_user(
    request: Request,
    session_id: SessionId,
    user_id: UserId,
    db: core_dependencies.DbSession,
) -> Response:
    """Delete a user session.

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
    sessions_service.delete_session(session_id, user_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/user/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["sessions:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_sessions_user(
    request: Request,
    user_id: UserId,
    db: core_dependencies.DbSession,
    exclude_session_id: Annotated[
        str | None,
        Query(description="Session to keep intact (e.g. the caller's current session)"),
    ] = None,
) -> Response:
    """Delete every session for a user, optionally keeping one intact.

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
    sessions_service.delete_sessions_by_user_and_commit(user_id, db, exclude_session_id=exclude_session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
