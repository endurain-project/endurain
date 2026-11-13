"""The signed-in user's own identity provider links, mounted under ``/profile/identity-providers``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, Security, status

import core.dependencies as core_dependencies
import core.network as core_network
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.account_security.identity_link_service as identity_link_service
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_provider_links.schema as auth_identity_links_schema
import modules.auth.identity_providers.schema as identity_providers_schema
import modules.auth.schema as auth_schema
import modules.users.users.schema as users_schema

router = APIRouter()


@router.post(
    "/{idp_id}/link",
    response_model=identity_providers_schema.BrowserFlowStartRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def start_idp_link(
    idp_id: core_dependencies.UuidId,
    link: users_schema.IdentityProviderLinkStart,
    request: Request,
    response: Response,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> identity_providers_schema.BrowserFlowStartRead:
    """Start linking an identity provider to the authenticated user's account.

    Linking enables persistent sign-in, so it needs step-up verification in ``step_up``: ``current_password`` (or, for an
    account without one, ``idp_reauth``), and an MFA code when MFA is enabled. The browser then follows
    ``authorization_url``, signs in at the provider, and the callback returns to ``redirect``. The response
    sets a cookie that binds the link to this browser.

    Args:
        idp_id: The identity provider to link.
        link: The frontend return path and the step-up verification.
        request: The incoming request, read by the rate limiter and for the client address.
        response: The response, which receives the browser-binding cookie.
        token_user_id: User ID from access token.
        token_session_id: Session ID from access token.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        The provider's authorization URL.
    """
    flow = identity_link_service.start_idp_link(
        idp_id,
        link,
        core_network.get_ip_address(request),
        token_user_id,
        token_session_id,
        step_up_store,
        db,
    )
    auth_dependencies.set_idp_browser_binding_cookie(response, flow.browser_binding)
    return identity_providers_schema.BrowserFlowStartRead(authorization_url=flow.authorization_url)


@router.post(
    "/{idp_id}/step-up",
    response_model=identity_providers_schema.BrowserFlowStartRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def start_idp_step_up(
    idp_id: core_dependencies.UuidId,
    start: identity_providers_schema.StepUpStartRequest,
    request: Request,
    response: Response,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> identity_providers_schema.BrowserFlowStartRead:
    """Start a fresh sign-in with a linked identity provider, for an account without a local password.

    Such an account has no password to prove, so a sensitive operation asks for this instead: the browser
    follows ``authorization_url``, the provider signs the user in again, and the callback returns to
    ``redirect`` with a single-use ``step_up_ticket`` in the URL fragment. The sensitive request then sends the
    ticket and the PKCE verifier of ``code_challenge`` as ``idp_reauth``. The response sets a cookie that binds
    the sign-in to this browser.

    Args:
        idp_id: The linked provider to sign in with again.
        start: The PKCE challenge, the operation and the return path.
        request: The incoming request, read by the rate limiter.
        response: The response, which receives the browser-binding cookie.
        token_user_id: User ID from access token.
        token_session_id: Session ID from access token.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        The provider's authorization URL.
    """
    flow = identity_link_service.start_idp_step_up(
        idp_id,
        start,
        core_network.get_ip_address(request),
        token_user_id,
        token_session_id,
        step_up_store,
        db,
    )
    auth_dependencies.set_idp_browser_binding_cookie(response, flow.browser_binding)
    return identity_providers_schema.BrowserFlowStartRead(authorization_url=flow.authorization_url)


# Identity Provider Management Endpoints
@router.get(
    "",
    response_model=auth_identity_links_schema.IdentityProviderLinkPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
def get_my_identity_providers(
    token_user_id: auth_dependencies.CurrentUserId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> auth_identity_links_schema.IdentityProviderLinkPage:
    """Retrieve one page of the authenticated user's identity provider links.

    Each link carries its connection metadata and the provider's name, slug, icon and type.

    Args:
        token_user_id: The authenticated user's ID from the access token.
        page: The requested window.
        db: Database session.

    Returns:
        The page of the user's identity provider links, oldest first.
    """
    return identity_link_service.get_user_identity_provider_links(token_user_id, page, db)


@router.post(
    "/{idp_id}/unlink",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def delete_my_identity_provider(
    idp_id: core_dependencies.UuidId,
    body: auth_schema.StepUpRequest,
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Delete (unlink) an identity provider from the authenticated user's account.

    This endpoint allows users to remove the association between their
    account and a specific identity provider. It requires step-up
    verification (current password or a fresh identity-provider
    sign-in, and MFA when enabled) and includes
    safety checks to prevent account lockout by ensuring users maintain
    at least one authentication method (either a password or another
    IdP link).

    Args:
        idp_id (uuid.UUID): The ID of the identity provider to unlink.
        body (StepUpRequest): The step-up verification.
        request (Request): The FastAPI request object.
        token_user_id (uuid.UUID): User ID extracted from the access token.
        token_session_id: Session ID from access token.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        None: Returns 204 No Content on successful deletion.

    Raises:
        DomainError (403): If step-up verification fails.
        DomainError (404): If the identity provider doesn't exist or
            is not linked to the user's account.
        DomainError (409): If attempting to unlink the last authentication method
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
    identity_link_service.delete_identity_provider_link(
        idp_id, body.step_up, token_user_id, token_session_id, step_up_store, db
    )
    return None
