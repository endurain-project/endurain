"""Public (unauthenticated) HTTP routes for identity provider SSO flows.

The routes translate HTTP; the decisions (PKCE, redirect checks, state binding, where to send the browser)
are :class:`~modules.auth.identity_providers.authorization_service.AuthorizationService`'s and
:class:`~modules.auth.identity_providers.callback_service.CallbackService`'s.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse

import core.config as core_config
import core.dependencies as core_dependencies
import core.network as core_network
import core.rate_limit as core_rate_limit
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.provider_service as idp_provider_service
import modules.auth.identity_providers.schema as idp_schema

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=list[idp_schema.IdentityProviderPublicRead],
)
def get_enabled_identity_providers(
    db: core_dependencies.DbSession,
) -> list[idp_schema.IdentityProviderPublicRead]:
    """Retrieve a list of enabled identity providers from the database.

    Args:
        db (Session): SQLAlchemy database session dependency.

    Returns:
        List[IdentityProviderPublic]: A list of enabled identity providers, each represented as an
        IdentityProviderPublic schema.
    """
    return idp_provider_service.get_enabled_identity_providers(db)


@router.get("/login/{idp_slug}", status_code=status.HTTP_307_TEMPORARY_REDIRECT, response_class=RedirectResponse)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def initiate_login(
    idp_slug: auth_dependencies.IdentityProviderSlug,
    request: Request,
    db: core_dependencies.DbSession,
    service: idp_dependencies.AuthorizationService,
    code_challenge: Annotated[
        str,
        Query(
            description=(
                "PKCE code challenge (base64url-encoded SHA256, 43-128 chars). REQUIRED for OAuth 2.1 compliance."
            ),
        ),
    ],
    code_challenge_method: Annotated[
        str,
        Query(
            description="PKCE method (must be S256). REQUIRED for OAuth 2.1 compliance.",
        ),
    ],
    redirect: Annotated[
        str | None,
        Query(
            alias="redirect",
            description="Frontend redirect path after successful login",
        ),
    ] = None,
):
    """Initiates the login process for a given identity provider using OAuth.

    PKCE (Proof Key for Code Exchange) is REQUIRED for all clients (OAuth 2.1 compliance).
    Both code_challenge and code_challenge_method=S256 must be provided.

    Rate Limit: 10 requests per minute per IP
    Args:
        idp_slug (str): The slug identifier for the identity provider.
        request (Request): The incoming HTTP request object.
        db (Session): Database session dependency.
        redirect (str | None): Optional frontend path to redirect to after login.
        code_challenge (str): PKCE code challenge (base64url-encoded SHA256, 43-128 chars). REQUIRED.
        code_challenge_method (str): PKCE method (only S256 supported). REQUIRED.

    Returns:
        RedirectResponse: A redirect response to the identity provider's authorization URL.

    Raises:
        NotFoundError: If the identity provider is not found or disabled.
        InvalidInputError: If PKCE validation or the redirect check fails.
    """
    authorization_url = service.begin_login(
        idp_slug,
        code_challenge,
        code_challenge_method,
        redirect,
        core_network.get_ip_address(request),
        request.headers.get("X-Client-Type"),
        core_config.settings.ALLOWED_REDIRECT_SCHEMES,
        db,
    )
    return RedirectResponse(url=authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/callback/{idp_slug}", status_code=status.HTTP_307_TEMPORARY_REDIRECT, response_class=RedirectResponse)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def handle_callback(
    request: Request,
    idp_slug: auth_dependencies.IdentityProviderSlug,
    password_hasher: Annotated[
        credentials_integration.PasswordHasher,
        Depends(credentials_integration.get_password_hasher),
    ],
    db: core_dependencies.DbSession,
    service: idp_dependencies.CallbackService,
    link_binding: idp_dependencies.LinkBinding = None,
    code: str = Query(..., description="Authorization code from IdP"),
    state: str = Query(..., description="State parameter for CSRF protection"),
):
    """Handle OAuth callback from an identity provider.

    This endpoint processes the OAuth authorization callback from external identity providers.
    It supports two modes: login mode (default) and link mode (for linking IdP to existing account).

    Args:
        request: The incoming HTTP request.
        idp_slug: The slug identifier of the identity provider.
        password_hasher: Password hasher dependency for session management.
        db: Database session dependency.
        service: Identity provider service.
        link_binding: The cookie that binds a link to the browser that started it.
        code: Authorization code received from the identity provider.
        state: State parameter used for CSRF protection (database state ID).

    Returns:
        RedirectResponse: A redirect response to either:
            - Settings page (link mode): /settings with success parameters
            - Login page (login mode): /login with session_id for token exchange
            - Error page: /login with error parameter if callback fails

    Raises:
        NotFoundError: If the identity provider is not found or disabled.
        InvalidInputError: If the state is unknown, expired, bound to another provider or already used.
            Any failure after the state is claimed redirects instead, so the browser never ends on a JSON error.

    Notes:
        - In link mode: Redirects to settings without creating a new session
        - In login mode: Creates session, redirects with session_id (client must exchange for tokens)
        - All clients must call /tokens exchange endpoint with PKCE verifier to get JWT tokens
        - On error: Redirects to login page with error parameter
        - All redirects use HTTP 307 (Temporary Redirect) status code
    """
    idp, oauth_state = service.prepare_callback(idp_slug, state, link_binding, db)
    redirect_url = service.complete_callback(
        idp,
        code,
        state,
        oauth_state,
        core_network.get_ip_address(request),
        core_network.get_user_agent(request),
        password_hasher,
        db,
    )
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    idp_dependencies.clear_link_binding_cookie(response)
    return response
