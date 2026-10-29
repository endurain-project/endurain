"""The signed-in user's own identity provider links, mounted under ``/profile/idp``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status

import core.dependencies as core_dependencies
import core.network as core_network
import core.rate_limit as core_rate_limit
import modules.auth.account_security.identity_link_service as identity_link_service
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_provider_link_tokens.schema as idp_link_token_schema
import modules.auth.identity_provider_links.schema as auth_identity_links_schema
import modules.users.users.schema as users_schema

router = APIRouter()


@router.post(
    "/{idp_id}/link/token",
    status_code=status.HTTP_201_CREATED,
    response_model=idp_link_token_schema.IdentityProviderLinkTokenRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def generate_link_token(
    idp_id: core_dependencies.PositiveId,
    link_request: idp_link_token_schema.IdpLinkTokenRequest,
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> idp_link_token_schema.IdentityProviderLinkTokenRead:
    """Generate a one-time token for linking an identity provider.

    This endpoint creates a short-lived (60 seconds), single-use token
    that can be used to securely initiate the OAuth flow for linking
    an identity provider to the authenticated user's account.

    Linking an identity provider is a sensitive operation that enables
    persistent authentication. Step-up verification is required: the
    caller MUST supply ``current_password``, and an MFA code when MFA
    is enabled on the account.

    This approach is more secure than passing access tokens in query
    parameters, as the link token:
    - Expires in 60 seconds
    - Can only be used once
    - Is scoped specifically for IdP linking
    - Limits exposure in server logs and browser history

    Args:
        idp_id (int): The ID of the identity provider to link.
        link_request (IdpLinkTokenRequest): Request with step-up credentials.
        request (Request): The FastAPI request object.
        token_user_id (int): The authenticated user's ID extracted from the access token.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        IdpLinkTokenResponse: Contains the one-time token and expiration time.

    Raises:
        DomainError:
            - 401 UNAUTHORIZED: If step-up verification fails.
            - 404 NOT_FOUND: If the identity provider doesn't exist or is disabled.
            - 409 CONFLICT: If the identity provider is already linked.
            - 500 INTERNAL_SERVER_ERROR: If token generation fails.
    """
    return identity_link_service.generate_link_token(
        idp_id, link_request, core_network.get_ip_address(request), token_user_id, step_up_store, db
    )


# Identity Provider Management Endpoints
@router.get(
    "",
    response_model=list[auth_identity_links_schema.IdentityProviderLinkRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def get_my_identity_providers(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> list[auth_identity_links_schema.IdentityProviderLinkRead]:
    """Retrieve all identity provider links for the authenticated user.

    This endpoint fetches all external identity provider (IdP) connections associated
    with the current user's account. Each link includes connection metadata and enriched
    details about the identity provider (name, slug, icon, and provider type).

    Args:
        token_user_id (int): The authenticated user's ID extracted from the JWT access token.
            Injected automatically via dependency injection.
        db: Database session.

    Returns:
        list[dict]: A list of dictionaries representing the user's IdP links. Each dictionary contains:
            - id (int): Unique identifier for the user-IdP link
            - user_id (int): ID of the user
            - idp_id (int): ID of the identity provider
            - idp_subject (str): User's unique identifier at the IdP
            - linked_at (datetime): Timestamp when the link was created
            - last_login (datetime): Timestamp of the last login via this IdP
            - idp_access_token_expires_at (datetime): Expiration time of the IdP access token
            - idp_refresh_token_updated_at (datetime): Last update time of the refresh token
            - idp_name (str): Display name of the identity provider (if available)
            - idp_slug (str): URL-safe identifier for the IdP (if available)
            - idp_icon (str): Icon/logo URL for the IdP (if available)
            - idp_provider_type (str): Type of provider (e.g., "oauth2", "oidc") (if available)

    Raises:
        DomainError: May raise authentication/authorization errors via the dependency injection.
    """
    return identity_link_service.get_user_identity_provider_links(token_user_id, db)


@router.post(
    "/{idp_id}/unlink",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def delete_my_identity_provider(
    idp_id: core_dependencies.PositiveId,
    step_up: users_schema.StepUpVerification,
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Delete (unlink) an identity provider from the authenticated user's account.

    This endpoint allows users to remove the association between their
    account and a specific identity provider. It requires step-up
    verification (current password and MFA when enabled) and includes
    safety checks to prevent account lockout by ensuring users maintain
    at least one authentication method (either a password or another
    IdP link).

    Args:
        idp_id (int): The ID of the identity provider to unlink.
        step_up (StepUpVerification): Step-up verification payload.
        request (Request): The FastAPI request object.
        token_user_id (int): User ID extracted from the access token.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        None: Returns 204 No Content on successful deletion.

    Raises:
        DomainError (401): If step-up verification fails.
        DomainError (404): If the identity provider doesn't exist or
            is not linked to the user's account.
        DomainError (400): If attempting to unlink the last authentication method
            without having a password set (prevents account lockout).
        DomainError (500): If the deletion operation fails at the database level.

    Notes:
        - Enforces step-up verification before unlinking.
        - Prevents account lockout by ensuring users have at least one
          authentication method (password or remaining IdP link).
        - Logs the unlinking action for audit purposes.
        - Uses token-based authentication to ensure users can only
          unlink their own IdPs.
    """
    identity_link_service.delete_identity_provider_link(idp_id, step_up, token_user_id, step_up_store, db)
    return None
