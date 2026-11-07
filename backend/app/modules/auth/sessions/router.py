"""Admin API endpoints for auth sessions, served under ``/users/{user_id}/sessions``."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Security, status
from starlette.responses import Response

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.auth.schema as auth_schema
import modules.auth.sessions.schema as sessions_schema
import modules.auth.sessions.service as sessions_service

router = APIRouter()


@router.get(
    "/{user_id}/sessions",
    response_model=sessions_schema.UserSessionsPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["sessions:read"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_READ)
def read_sessions_user(
    request: Request,
    user_id: core_dependencies.PositiveId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> sessions_schema.UserSessionsPage:
    """Retrieve one page of the sessions associated with a specific user.

    Args:
        user_id: The ID of the user whose sessions to retrieve.
        page: The requested window.
        db: Database session dependency.
        request: Incoming request.

    Returns:
        The page of session objects for the specified user.
    """
    return sessions_service.list_user_sessions(user_id, page, db)


@router.post(
    "/{user_id}/sessions/{session_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["sessions:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def revoke_session_user(
    request: Request,
    session_id: auth_dependencies.AuthSessionId,
    user_id: core_dependencies.PositiveId,
    body: auth_schema.StepUpRequest,
    db: core_dependencies.DbSession,
    verify_step_up: auth_dependencies.SessionRevokeVerifierDep,
) -> Response:
    """End one session of a user.

    Needs the administrator's own step-up verification in `step_up`, as ending a session locks the user out.

    Args:
        session_id: The ID of the session to end.
        user_id: The ID of the user who owns the session.
        body: The administrator's step-up verification.
        db: Database session dependency.
        verify_step_up: Verifies the administrator's step-up.
        request: Incoming request.

    Returns:
        None.

    Raises:
        HTTPException: 403 if the step-up fails, 404 if the session is not found.
    """
    sessions_service.delete_session(session_id, user_id, body.step_up, verify_step_up, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{user_id}/sessions/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["sessions:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def revoke_sessions_user(
    request: Request,
    user_id: core_dependencies.PositiveId,
    body: auth_schema.StepUpRequest,
    db: core_dependencies.DbSession,
    verify_step_up: auth_dependencies.SessionRevokeVerifierDep,
    exclude_session_id: Annotated[
        str | None,
        Query(description="Session to keep intact (e.g. the caller's current session)"),
    ] = None,
) -> Response:
    """End every session of a user, optionally keeping one intact.

    Needs the administrator's own step-up verification in `step_up`, as ending sessions locks the user out.
    Pass the caller's current ``exclude_session_id`` to sign out every other device while staying logged in, or
    omit it to end all of that user's sessions.

    Args:
        user_id: The ID of the user whose sessions to end.
        body: The administrator's step-up verification.
        db: Database session dependency.
        verify_step_up: Verifies the administrator's step-up.
        exclude_session_id: Optional session to leave intact.
        request: Incoming request.

    Returns:
        None.

    Raises:
        HTTPException: 403 if the step-up fails.
    """
    sessions_service.delete_sessions_by_user_and_commit(
        user_id, body.step_up, verify_step_up, db, exclude_session_id=exclude_session_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
