"""The signed-in user's own sessions, mounted under ``/profile/sessions``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, Security, status

import core.config as core_config
import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.auth.sessions.schema as auth_sessions_schema

router = APIRouter()


@router.get(
    "",
    response_model=auth_sessions_schema.UserSessionsPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile:security"])],
)
def read_sessions_me(
    token_user_id: auth_dependencies.CurrentUserId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> auth_sessions_schema.UserSessionsPage:
    """Retrieve one page of the authenticated user's sessions.

    Args:
        token_user_id: User ID from access token.
        page: The requested window.
        db: Database session.

    Returns:
        The page of session objects for the user.
    """
    return account_security_service.list_user_sessions(token_user_id, page, db)


@router.post(
    "/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def revoke_profile_sessions(
    request: Request,
    response: Response,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: Annotated[
        str,
        Depends(auth_dependencies.get_sid_from_access_token),
    ],
    db: core_dependencies.DbSession,
    keep_current: Annotated[
        bool,
        Query(description="Keep the caller's current session and end only the others"),
    ] = False,
) -> None:
    """Sign out everywhere, or only on the other devices.

    By default every session of the authenticated user ends, the current one included, so the client must discard
    its tokens and send the user to the login page; the browser's refresh-token cookie is cleared on the response.
    With `keep_current=true` every other session ends and the caller stays signed in, so the cookie is left alone.

    Args:
        request: The incoming request, read by the rate limiter.
        response: The response, on which the refresh-token cookie is cleared.
        token_user_id: User ID from access token.
        token_session_id: The caller's current session, preserved when `keep_current` is set.
        db: Database session.
        keep_current: Whether to keep the caller's current session.

    Returns:
        None.
    """
    if keep_current:
        account_security_service.delete_other_user_sessions(token_user_id, token_session_id, db)
        return
    account_security_service.sign_out_everywhere(token_user_id, db)
    authentication_dependencies.clear_refresh_token_cookies(response, environment=core_config.settings.ENVIRONMENT)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile:security"])],
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
