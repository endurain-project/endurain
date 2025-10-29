"""
User Identity Provider Router

Handles admin operations for managing user identity provider links.
These endpoints allow administrators to view and manage which external
authentication providers are linked to user accounts.

Security:
    - Admin-only endpoints (sessions:read, sessions:write scopes)
    - Does NOT expose refresh tokens (security)
    - Audit logging handled by CRUD layer
"""

from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session

import core.database as core_database
import core.logger as core_logger
import auth.security as auth_security
import users.user_identity_providers.crud as user_idp_crud
import users.user_identity_providers.schema as user_idp_schema
import users.user.schema as users_schema
import users.user.crud as users_crud
import auth.identity_providers.crud as idp_crud


# Define the API router
router = APIRouter()


@router.get(
    "/users/{user_id}/identity-providers",
    response_model=List[user_idp_schema.UserIdentityProviderResponse],
    status_code=status.HTTP_200_OK,
)
async def get_user_identity_providers(
    user_id: int,
    db: Annotated[Session, Depends(core_database.get_db)],
    _check_scopes: Annotated[
        users_schema.UserRead,
        Security(auth_security.check_scopes, scopes=["sessions:read"]),
    ],
):
    """
    Retrieve all identity provider links for a specific user with enriched IDP details.
    This endpoint fetches all external identity providers (OAuth, OIDC, etc.) linked to a user's account
    and enriches the response with additional provider information for frontend display purposes.
    Args:
        user_id (int): The ID of the user whose identity provider links to retrieve.
        db (Session): Database session dependency injected by FastAPI.
        _check_scopes (UserRead): Security dependency that validates the user has 'sessions:read' scope.
    Returns:
        list[dict]: A list of dictionaries containing enriched identity provider link information.
            Each dictionary includes:
            - id: The link's unique identifier
            - user_id: The user's ID
            - idp_id: The identity provider's ID
            - idp_subject: The user's identifier in the external IDP
            - linked_at: Timestamp when the link was created
            - last_login: Timestamp of the last login via this IDP
            - idp_access_token_expires_at: When the access token expires
            - idp_refresh_token_updated_at: When the refresh token was last updated
            - idp_name: The identity provider's display name
            - idp_slug: The identity provider's URL-friendly identifier
            - idp_icon: Icon/logo URL for the identity provider
            - idp_provider_type: Type of provider (e.g., 'oauth2', 'oidc')
    Raises:
        HTTPException: 404 error if the user with the specified ID does not exist.
    Example:
        ```
        [
            {
                "id": 1,
                "user_id": 123,
                "idp_id": 5,
                "idp_subject": "google-user-123456",
                "linked_at": "2024-01-15T10:30:00",
                "last_login": "2024-01-20T14:25:00",
                "idp_name": "Google",
                "idp_slug": "google",
                "idp_icon": "https://example.com/google-icon.png",
                "idp_provider_type": "oauth2"
        ]
        ```
    """
    # Validate user exists
    user = users_crud.get_user_by_id(user_id, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )

    # Get user's identity provider links
    idp_links = user_idp_crud.get_user_identity_providers_by_user_id(user_id, db)

    # Enrich with IDP details for frontend display
    enriched_links = []
    for link in idp_links:
        # Convert SQLAlchemy model to dict
        link_dict = {
            "id": link.id,
            "user_id": link.user_id,
            "idp_id": link.idp_id,
            "idp_subject": link.idp_subject,
            "linked_at": link.linked_at,
            "last_login": link.last_login,
            "idp_access_token_expires_at": link.idp_access_token_expires_at,
            "idp_refresh_token_updated_at": link.idp_refresh_token_updated_at,
        }

        # Fetch IDP details for display
        idp = idp_crud.get_identity_provider(link.idp_id, db)
        if idp:
            link_dict["idp_name"] = idp.name
            link_dict["idp_slug"] = idp.slug
            link_dict["idp_icon"] = idp.icon
            link_dict["idp_provider_type"] = idp.provider_type

        enriched_links.append(link_dict)

    return enriched_links


@router.delete(
    "/users/{user_id}/identity-providers/{idp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_identity_provider(
    user_id: int,
    idp_id: int,
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    _check_scopes: Annotated[
        users_schema.UserRead,
        Security(auth_security.check_scopes, scopes=["sessions:write"]),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Delete a link between a user and an identity provider.
    This endpoint removes the association between a specified user and identity provider.
    It validates that both the user and identity provider exist before attempting deletion.
    Requires admin privileges (sessions:write scope).
    Args:
        user_id (int): The ID of the user whose identity provider link should be deleted.
        idp_id (int): The ID of the identity provider to unlink from the user.
        db (Session): Database session dependency injected by FastAPI.
        admin_user (users_schema.UserRead): The authenticated admin user performing the operation,
            verified by session security with sessions:write scope.
    Returns:
        None: Returns 204 No Content on successful deletion.
    Raises:
        HTTPException: 404 Not Found if the user with the specified user_id doesn't exist.
        HTTPException: 404 Not Found if the identity provider with the specified idp_id doesn't exist.
        HTTPException: 404 Not Found if no link exists between the specified user and identity provider.
    Note:
        This operation is logged for audit purposes, recording the admin user who performed
        the deletion along with the user and identity provider details.
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
    success = user_idp_crud.delete_user_identity_provider(user_id, idp_id, db)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Identity provider link not found for user {user_id} and IDP {idp_id}",
        )

    # Audit logging
    core_logger.print_to_log(
        f"Admin user {token_user_id} deleted IDP link: "
        f"user_id={user_id}, idp_id={idp_id} ({idp.name})"
    )

    # Return 204 No Content (successful deletion)
    return None
