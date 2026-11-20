"""The signed-in user's own sessions, mounted under ``/profile/sessions``."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, Security, status

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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
def read_sessions_me(
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.OptionalSessionId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> auth_sessions_schema.UserSessionsPage:
    """Retrieve one page of the authenticated user's sessions.

    `is_current` marks the session the request is made from; it is false for every item when an API key calls.
    """
    return account_security_service.list_user_sessions(token_user_id, page, db, token_session_id)


@router.post(
    "/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def revoke_profile_sessions(
    request: Request,
    response: Response,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_profile_session(
    request: Request,
    session_id: auth_dependencies.AuthSessionId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Delete user session from database."""
    account_security_service.delete_user_session(session_id, token_user_id, db)
