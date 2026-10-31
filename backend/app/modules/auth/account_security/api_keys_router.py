"""The signed-in user's API-key management routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.account_security.api_key_service as api_key_service
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "",
    response_model=api_keys_schema.UsersApiKeyPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def list_user_api_keys(
    token_user_id: auth_dependencies.CurrentUserId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> api_keys_schema.UsersApiKeyPage:
    """List one page of API keys for the authenticated user.

    Args:
        token_user_id: User ID from access token.
        page: The requested window.
        db: Database session.

    Returns:
        The page of API keys, newest first.
    """
    return api_key_service.list_user_api_keys(token_user_id, page, db)


@router.post(
    "",
    response_model=api_keys_schema.UsersApiKeyCreatedRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def create_user_api_key(
    data: api_keys_schema.UsersApiKeyCreate,
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> api_keys_schema.UsersApiKeyCreatedRead:
    """Create an API key after step-up verification."""
    return api_key_service.create_user_api_key(token_user_id, token_session_id, data, step_up_store, db)


@router.post(
    "/{api_key_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def revoke_user_api_key(
    api_key_id: auth_dependencies.ApiKeyId,
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Revoke an API key owned by the authenticated user."""
    api_key_service.revoke_user_api_key(api_key_id, token_user_id, db)


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def delete_user_api_key(
    api_key_id: auth_dependencies.ApiKeyId,
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Permanently delete an API key owned by the authenticated user."""
    api_key_service.delete_user_api_key(api_key_id, token_user_id, db)
