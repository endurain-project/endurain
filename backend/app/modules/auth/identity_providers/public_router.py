"""Public (unauthenticated) HTTP routes for identity provider SSO flows.

The routes translate HTTP; the decisions (PKCE, redirect checks, state binding, where to send the browser)
are :class:`~modules.auth.identity_providers.authorization_service.AuthorizationService`'s and
:class:`~modules.auth.identity_providers.callback_service.CallbackService`'s.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse

import core.cache_control as core_cache_control
import core.config as core_config
import core.dependencies as core_dependencies
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.network as core_network
import core.openapi_contract as core_openapi_contract
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.icon_service as idp_icon_service
import modules.auth.identity_providers.link_ticket_store as idp_link_ticket_store
import modules.auth.identity_providers.provider_service as idp_provider_service
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.oauth_state.constants as oauth_state_constants

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=idp_schema.IdentityProviderPublicPage,
)
def get_enabled_identity_providers(
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> idp_schema.IdentityProviderPublicPage:
    """Retrieve one page of the enabled identity providers."""
    return idp_provider_service.get_enabled_identity_providers(page, db)


@router.get(
    "/login/{idp_slug}",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
    responses={
        400: {
            "description": "The PKCE challenge is missing or malformed, the redirect is not allowed, or the "
            "provider's authorization endpoint is not a public address."
        },
        502: {"description": "The provider's authorization endpoint could not be resolved."},
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def initiate_login(
    idp_slug: auth_dependencies.IdentityProviderSlug,
    request: Request,
    db: core_dependencies.DbSession,
    service: idp_dependencies.AuthorizationService,
    code_challenge: Annotated[
        str,
        Query(
            description=("PKCE code challenge (base64url-encoded SHA256, 43-128 chars). Required (RFC 7636)."),
        ),
    ],
    code_challenge_method: Annotated[
        str,
        Query(
            description="PKCE method (must be S256). Required (RFC 7636).",
        ),
    ],
    redirect: Annotated[
        str | None,
        Query(
            alias="redirect",
            max_length=oauth_state_constants.REDIRECT_MAX_LENGTH,
            description="Frontend redirect path after successful login",
        ),
    ] = None,
) -> RedirectResponse:
    """Initiates the login process for a given identity provider using OAuth.

    PKCE (Proof Key for Code Exchange) is REQUIRED for all clients (RFC 7636, S256 only).
    Both code_challenge and code_challenge_method=S256 must be provided.

    The client type comes from the redirect alone: a native-app redirect starts a mobile flow, anything else
    a web flow. The request needs no `X-Client-Type` header and ignores one.

    Rate Limit: 10 requests per minute per IP
    """
    start = service.begin_login(
        idp_slug,
        code_challenge,
        code_challenge_method,
        redirect,
        core_network.get_ip_address(request),
        core_config.settings.ALLOWED_REDIRECT_URIS,
        db,
    )
    response = RedirectResponse(url=start.authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    idp_dependencies.set_browser_binding_cookie(response, start.browser_binding)
    return response


@router.get(
    "/link",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
    responses={400: {"description": "The ticket is unknown, expired or already used."}},
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def start_link_in_browser(
    request: Request,
    state: core_dependencies.PlatformState,
    ticket: Annotated[
        str,
        Query(min_length=1, max_length=128, description="The single-use ticket the link start answered."),
    ],
) -> RedirectResponse:
    """Hand a link a native app started to the system browser: bind the browser, then send it to the provider.

    A native app starts a link with an authenticated request, but the provider's callback must arrive in a browser
    that holds the binding of the flow, and the app's HTTP client is not that browser. The start request answers with
    the URL of this route and a single-use ticket that lives two minutes; the app opens it in the system browser, which
    receives the binding cookie here and is redirected to the provider. The ticket is spent by the first request, so
    a second browser that obtains the URL later gets a 400. Rate limit: 10 requests per minute per IP.
    """
    link = idp_link_ticket_store.LinkTicketStore(state).redeem(ticket)
    if link is None:
        raise core_exceptions.InvalidInputError("Invalid or expired link ticket")
    response = RedirectResponse(url=link.authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    idp_dependencies.set_browser_binding_cookie(response, link.browser_binding)
    return response


@router.get(
    "/callback/{idp_slug}",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
    responses={
        400: {
            "description": "The `state` is unknown, expired, already used, bound to another provider, or not "
            "from the browser that started the flow."
        }
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def handle_callback(
    request: Request,
    idp_slug: auth_dependencies.IdentityProviderSlug,
    db: core_dependencies.DbSession,
    service: idp_dependencies.CallbackService,
    browser_binding: idp_dependencies.BrowserBinding = None,
    code: str | None = Query(None, description="Authorization code from IdP"),
    error: str | None = Query(None, max_length=128, description="Error the IdP returned instead of a code"),
    state: str = Query(..., description="State parameter for CSRF protection"),
    iss: str | None = Query(None, max_length=2048, description="Issuer the provider identifies itself with"),
) -> RedirectResponse:
    """Handle OAuth callback from an identity provider.

    This endpoint processes the OAuth authorization callback from external identity providers.
    It finishes a login, a link of the provider to the signed-in account, or a step-up re-authentication.

    Every outcome is an HTTP 307 redirect, so the browser never ends on a JSON error once the state is claimed:

    - Link: back to `/settings` without a new session.
    - Login: to `/login` with a `session_id`; the client exchanges it, with its PKCE verifier, at the `/tokens`
      endpoint for the JWT tokens.
    - Step-up: to the page that started it, with the ticket or the error in the fragment.
    - Failure: to `/login` with an `error` parameter.
    """
    idp, oauth_state = service.prepare_callback(idp_slug, state, browser_binding, db)
    redirect_url = service.complete_callback(
        idp,
        code,
        error,
        state,
        oauth_state,
        core_network.get_ip_address(request),
        core_network.get_user_agent(request),
        db,
        iss=iss,
    )
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    idp_dependencies.clear_browser_binding_cookie(response)
    return response


@router.get(
    "/{idp_slug}/icon",
    response_class=Response,
    responses={
        **core_openapi_contract.binary_response("image/*", description="The provider icon."),
        304: {"description": "Not modified"},
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def read_identity_provider_icon(
    idp_slug: auth_dependencies.IdentityProviderSlug,
    request: Request,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> Response:
    """Serve the uploaded icon of an identity provider (unauthenticated).

    The login screen renders before anyone is signed in, so the icon is public by design; it is one
    admin-chosen image, not user data. The response carries an ETag derived from the provider version and must
    be revalidated, so a replaced icon shows at once while a client that holds it gets a 304 without storage
    being read.
    """
    found = idp_icon_service.get_public_icon(idp_slug, db)
    if found is None:
        raise core_exceptions.NotFoundError("Identity provider icon not found")
    idp_id, version = found
    headers = {"Cache-Control": "public, no-cache", "ETag": core_etag.format_etag(version)}
    if core_etag.matches_if_none_match(request.headers.get("if-none-match"), version):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    icon = idp_icon_service.read_icon(idp_id, storage)
    if icon is None:
        raise core_exceptions.NotFoundError("Identity provider icon not found")
    data, media_type = icon
    return Response(content=data, media_type=media_type, headers=headers)


@router.post(
    "/{idp_slug}/backchannel-logout",
    response_class=Response,
    responses={
        200: {
            "description": "The sessions the logout token names have ended, or none was signed in.",
            "headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS,
        },
        400: {
            "description": "The logout token was refused: it does not verify, was already used, or the provider's "
            "signing keys could not be read."
        },
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.DEFAULT)
def backchannel_logout(
    request: Request,
    idp_slug: auth_dependencies.IdentityProviderSlug,
    logout_token: idp_dependencies.LogoutToken,
    db: core_dependencies.DbSession,
    service: idp_dependencies.BackchannelLogoutService,
) -> Response:
    """Receive an OpenID Connect Back-Channel Logout request from an identity provider.

    Register this URL at the provider as its back-channel logout URI. The provider posts a signed `logout_token`
    (`application/x-www-form-urlencoded`) when the user signs out there; Endurain verifies it against the provider's
    signing keys and ends the sessions it names: those signed in under its `sid`, only the user's when a `sub` is
    named too, or every session the user signed in to through the provider when only a `sub` is named. A token is
    accepted once. The answer is 200 with no body when the sessions ended or none was signed in, and 400 when the
    token is refused. A provider that does not exist or issues no ID token answers 404; a disabled provider is still
    served, so a logout token for a sign-in recorded before it was disabled still succeeds.
    """
    service.logout(idp_slug, logout_token, db)
    return Response(headers=core_cache_control.NO_STORE_HEADERS)
