"""The signed-in user's own sessions, mounted under ``/profile/sessions``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.dependencies as auth_dependencies
import modules.auth.sessions.schema as auth_sessions_schema

router = APIRouter()


@router.get(
    "",
    response_model=auth_sessions_schema.UsersSessionsPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def read_sessions_me(
    token_user_id: auth_dependencies.CurrentUserId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> auth_sessions_schema.UsersSessionsPage:
    """Retrieve one page of the authenticated user's sessions.

    Args:
        token_user_id: User ID from access token.
        page: The requested window.
        db: Database session.

    Returns:
        The page of session objects for the user.
    """
    return account_security_service.list_user_sessions(token_user_id, page, db)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_profile_other_sessions(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: Annotated[
        str,
        Depends(auth_dependencies.get_sid_from_access_token),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Revoke all of the authenticated user's other sessions.

    Signs out every device except the caller's current session
    (identified from the access token), so a user can end all
    other sessions without logging themselves out. This is the
    standalone form of the password change's
    ``revoke_other_sessions`` option.

    Args:
        request: The incoming request, read by the rate limiter.
        token_user_id: User ID from access token.
        token_session_id: The caller's current session, preserved.
        db: Database session.

    Returns:
        None.
    """
    account_security_service.delete_other_user_sessions(token_user_id, token_session_id, db)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_profile_session(
    request: Request,
    session_id: auth_dependencies.AuthSessionId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Delete user session from database.

    Args:
        request: The incoming request, read by the rate limiter.
        session_id: Session identifier to delete.
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        None.
    """
    account_security_service.delete_user_session(session_id, token_user_id, db)
