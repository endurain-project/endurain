"""
User Identity Provider Router.

Handles admin operations for managing user identity provider links.
These endpoints allow administrators to view and manage which external
authentication providers are linked to user accounts.

Security:
    - Admin-only endpoints (sessions:read, sessions:write scopes)
    - Does NOT expose refresh tokens (security)
    - Audit logging handled by CRUD layer
"""

from typing import Annotated
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Security,
)
from sqlalchemy.orm import Session

import core.database as core_database
import core.logger as core_logger
import auth.security as auth_security
import users.user_identity_providers.crud as user_idp_crud
import users.user_identity_providers.schema as user_idp_schema
import users.user_identity_providers.utils as user_idp_utils
import users.user.schema as users_schema
import users.user.crud as users_crud
import auth.identity_providers.crud as idp_crud


# Define the API router
router = APIRouter()


@router.get(
    "/users/{user_id}/identity-providers",
    response_model=list[user_idp_schema.UserIdentityProviderResponse],
    status_code=status.HTTP_200_OK,
)
async def get_user_identity_providers(
    user_id: int,
    db: Annotated[Session, Depends(core_database.get_db)],
    _check_scopes: Annotated[
        users_schema.UserRead,
        Security(
            auth_security.check_scopes,
            scopes=["sessions:read"],
        ),
    ],
) -> list[user_idp_schema.UserIdentityProviderResponse]:
    """
    Retrieve all identity provider links with enriched details.

    Args:
        user_id: User ID whose IdP links to retrieve.
        db: Database session.
        _check_scopes: Security dependency for sessions:read.

    Returns:
        List of enriched identity provider links.

    Raises:
        HTTPException: 404 if user not found.
    """
    # Validate user exists
    user = users_crud.get_user_by_id(user_id, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )

    # Get user's identity provider links
    idp_links = user_idp_crud.get_user_identity_providers_by_user_id(
        user_id,
        db,
    )

    # Enrich with IDP details (batch fetch to avoid N+1 queries)
    return user_idp_utils.enrich_user_identity_providers(
        idp_links,
        user_id,
        db,
    )


@router.delete(
    "/users/{user_id}/identity-providers/{idp_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_identity_provider(
    user_id: int,
    idp_id: int,
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[
        users_schema.UserRead,
        Security(
            auth_security.check_scopes,
            scopes=["sessions:write"],
        ),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> None:
    """
    Delete link between user and identity provider.

    Validates existence before deletion. Logs for audit.

    Args:
        user_id: User ID to unlink.
        idp_id: Identity provider ID to unlink.
        token_user_id: Admin user performing the operation.
        _check_scopes: Security dependency for sessions:write.
        db: Database session.

    Returns:
        None (204 No Content).

    Raises:
        HTTPException: 404 if user, IdP, or link not found.
    """
    # Validate user exists
    user = users_crud.get_user_by_id(user_id, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )

    # Validate IDP exists
    idp = idp_crud.get_identity_provider(idp_id, db)
    if idp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Identity provider with id {idp_id} not found",
        )

    # Attempt to delete the link
    success = user_idp_crud.delete_user_identity_provider(
        user_id,
        idp_id,
        db,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Identity provider link not found for "
                f"user {user_id} and IDP {idp_id}"
            ),
        )

    # Audit logging
    core_logger.print_to_log(
        f"Admin user {token_user_id} deleted IDP link: "
        f"user_id={user_id}, idp_id={idp_id} ({idp.name})"
    )

    return None
