"""The signed-in user's own sessions, mounted under ``/profile/sessions``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, Security, status

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


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile:security"])],
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
    db: core_dependencies.DbSession,
) -> None:
    """Sign out everywhere: end every session of the authenticated user, the current one included.

    Every device is signed out, this one too, so the client must discard its tokens and send the user to the
    login page. The browser's refresh-token cookie is cleared on the response. Unlike ending the other sessions,
    which keeps the caller signed in, this leaves no session behind.
    """
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
