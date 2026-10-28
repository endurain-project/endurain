"""The signed-in user's API-key management routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Security, status

import core.dependencies as core_dependencies
import modules.auth.account_security.api_key_service as api_key_service
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_service as identity_service_module

router = APIRouter()


@router.get("", response_model=list[api_keys_schema.UsersApiKeyRead])
def get_user_api_keys(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    _: Annotated[None, Security(auth_dependencies.check_scopes, scopes=["profile"])],
) -> list[api_keys_schema.UsersApiKeyRead]:
    """List API keys for the authenticated user."""
    return api_key_service.get_user_api_keys(token_user_id, db)


@router.post("", response_model=api_keys_schema.UsersApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_user_api_key(
    data: api_keys_schema.UsersApiKeyCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    identity_service: Annotated[
        identity_service_module.IdentityService,
        Depends(identity_service_module.get_identity_service),
    ],
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
    _: Annotated[None, Security(auth_dependencies.check_scopes, scopes=["profile"])],
) -> api_keys_schema.UsersApiKeyCreated:
    """Create an API key after step-up verification."""
    return api_key_service.create_user_api_key(token_user_id, data, identity_service, step_up_store, db)


@router.patch("/{api_key_id}/revoke", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def revoke_user_api_key(
    api_key_id: str,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    _: Annotated[None, Security(auth_dependencies.check_scopes, scopes=["profile"])],
) -> None:
    """Revoke an API key owned by the authenticated user."""
    api_key_service.revoke_user_api_key(api_key_id, token_user_id, db)


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_user_api_key(
    api_key_id: str,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    _: Annotated[None, Security(auth_dependencies.check_scopes, scopes=["profile"])],
) -> None:
    """Permanently delete an API key owned by the authenticated user."""
    api_key_service.delete_user_api_key(api_key_id, token_user_id, db)
