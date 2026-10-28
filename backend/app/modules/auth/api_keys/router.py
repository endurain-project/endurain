"""User API key management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

import core.dependencies as core_dependencies
import modules.auth._internal.internal_dependencies as auth_internal_dependencies
import modules.auth._internal.services.step_up_service as step_up_service
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.api_keys.service as api_keys_service
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_service as auth_identity_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=list[api_keys_schema.UsersApiKeyRead],
    status_code=status.HTTP_200_OK,
)
async def get_user_api_keys(
    token_user_id: Annotated[
        int,
        Depends(auth_internal_dependencies.get_sub_from_access_token),
    ],
    db: core_dependencies.DbSession,
) -> list[api_keys_schema.UsersApiKeyRead]:
    """
    Retrieve all API keys for the authenticated user.

    Args:
        token_user_id: User ID from access token.
        db: Database session dependency.

    Returns:
        List of API key objects. Raw keys and hashes
        are never included.
    """
    return api_keys_service.get_user_api_keys(token_user_id, db)


@router.post(
    "",
    response_model=api_keys_schema.UsersApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_api_key(
    data: api_keys_schema.UsersApiKeyCreate,
    token_user_id: Annotated[
        int,
        Depends(auth_internal_dependencies.get_sub_from_access_token),
    ],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> api_keys_schema.UsersApiKeyCreated:
    """
    Create a new API key for the authenticated user.

    The raw key is returned once in this response and
    cannot be retrieved again. Requested scopes must be
    supported by API-key authentication.

    Step-up verification is required (current password,
    plus MFA code when MFA is enabled). API keys grant
    persistent, long-lived access — a stolen access
    token alone must not be sufficient to mint one.

    Args:
        data: Key creation data (name, scopes, expiry,
            step-up credentials).
        token_user_id: User ID from access token.
        identity_service: Identity service dependency.
        db: Database session dependency.

    Returns:
        Created API key including the raw key string.

    Raises:
        HTTPException: 401 if step-up verification fails.
        HTTPException: 400 if scopes are not supported for API keys.
        HTTPException: 404 if the user is not found.
    """
    step_up_service.verify_step_up_credentials(
        token_user_id,
        data.current_password,
        data.mfa_code,
        identity_service,
        step_up_store,
        db,
    )

    return api_keys_service.create_user_api_key(token_user_id, data, db)


@router.patch(
    "/{api_key_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_user_api_key(
    api_key_id: str,
    token_user_id: Annotated[
        int,
        Depends(auth_internal_dependencies.get_sub_from_access_token),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """
    Revoke an API key (soft-disable).

    The key record is retained for audit purposes but
    will be rejected on any subsequent use.

    Args:
        api_key_id: UUID of the API key to revoke.
        token_user_id: User ID from access token.
        db: Database session dependency.

    Returns:
        None.

    Raises:
        HTTPException: 404 if the key is not found or
            does not belong to the authenticated user.
    """
    api_keys_service.revoke_user_api_key(api_key_id, token_user_id, db)


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_api_key(
    api_key_id: str,
    token_user_id: Annotated[
        int,
        Depends(auth_internal_dependencies.get_sub_from_access_token),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """
    Permanently delete an API key.

    Hard-delete. The key is gone and cannot be used
    or recovered after this operation.

    Args:
        api_key_id: UUID of the API key to delete.
        token_user_id: User ID from access token.
        db: Database session dependency.

    Returns:
        None.

    Raises:
        HTTPException: 404 if the key is not found or
            does not belong to the authenticated user.
    """
    api_keys_service.delete_user_api_key(api_key_id, token_user_id, db)
