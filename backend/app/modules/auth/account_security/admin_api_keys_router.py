"""Administrator routes for another user's API keys, served under ``/users/{user_id}/api-keys``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.account_security.api_key_service as api_key_service
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.dependencies as auth_dependencies
import modules.auth.schema as auth_schema

router = APIRouter()


@router.get(
    "/{user_id}/api-keys",
    response_model=api_keys_schema.UserApiKeyPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["api-keys:read"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_READ)
def read_api_keys_user(
    request: Request,
    user_id: core_dependencies.UuidId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> api_keys_schema.UserApiKeyPage:
    """List one page of a user's API keys, newest first. A key's secret is never returned."""
    return api_key_service.list_api_keys_of_user(user_id, page, db)


@router.post(
    "/{user_id}/api-keys/{api_key_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["api-keys:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def revoke_api_key_user(
    api_key_id: auth_dependencies.ApiKeyId,
    user_id: core_dependencies.UuidId,
    body: auth_schema.StepUpRequest,
    request: Request,
    admin_id: auth_dependencies.CurrentUserId,
    admin_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Revoke one API key of a user, which stops it from authenticating, and tell the user.

    Needs the administrator's own step-up verification in `step_up`. `404` when the user has no such key.
    """
    api_key_service.revoke_api_key_of_user(
        api_key_id, user_id, admin_id, admin_session_id, body.step_up, step_up_store, db
    )


@router.post(
    "/{user_id}/api-keys/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["api-keys:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def revoke_api_keys_user(
    user_id: core_dependencies.UuidId,
    body: auth_schema.StepUpRequest,
    request: Request,
    admin_id: auth_dependencies.CurrentUserId,
    admin_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Revoke every active API key of a user and tell the user.

    Needs the administrator's own step-up verification in `step_up`.
    """
    api_key_service.revoke_api_keys_of_user(user_id, admin_id, admin_session_id, body.step_up, step_up_store, db)
