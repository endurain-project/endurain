"""The signed-in user's own sessions, mounted under ``/profile/sessions``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status

import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_service as auth_identity_service
import modules.auth.sessions.schema as auth_sessions_schema

router = APIRouter()

#: The identifier of one of the caller's sessions, as the auth boundary issued it.
SessionId = Annotated[str, Path(min_length=1)]


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[auth_sessions_schema.UsersSessionsRead],
)
def read_sessions_me(
    token_user_id: auth_dependencies.CurrentUserId,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> list[auth_sessions_schema.UsersSessionsRead]:
    """Retrieve all sessions for authenticated user.

    Args:
        token_user_id: User ID from access token.
        identity_service: Identity service dependency.

    Returns:
        List of session objects for the user.
    """
    return identity_service.get_user_sessions(token_user_id)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_profile_other_sessions(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: Annotated[
        str,
        Depends(auth_dependencies.get_sid_from_access_token),
    ],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
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
        identity_service: Identity service dependency.

    Returns:
        None.
    """
    identity_service.delete_other_user_sessions(token_user_id, token_session_id)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_profile_session(
    request: Request,
    session_id: SessionId,
    token_user_id: auth_dependencies.CurrentUserId,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> None:
    """Delete user session from database.

    Args:
        request: The incoming request, read by the rate limiter.
        session_id: Session identifier to delete.
        token_user_id: User ID from access token.
        identity_service: Identity service dependency.

    Returns:
        None.
    """
    identity_service.delete_user_session(session_id, token_user_id)
