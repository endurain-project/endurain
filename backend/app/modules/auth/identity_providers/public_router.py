"""Public (unauthenticated) HTTP routes for identity provider SSO flows."""

from typing import Annotated
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

import core.config as core_config
import core.dependencies as core_dependencies
import core.hashing as core_hashing
import core.logger as core_logger
import core.network as core_network
import core.rate_limit as core_rate_limit
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.computation as auth_computation
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.identity_providers.utils as idp_utils

# Define the API router
router = APIRouter()


def _append_query_params(url: str, params: dict[str, str]) -> str:
    """Append query parameters to a URL or relative path, preserving any existing query."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _build_link_result_url(redirect_path: str | None, idp_name: str | None, *, success: bool) -> str:
    """Build the post-link redirect that carries the result to the originating client.

    Honors a caller-supplied return path captured at link initiation (validated
    there against open redirects): a relative path is resolved against the
    configured frontend host, while a custom URI scheme is handed off directly to
    the native client. Falls back to the security settings path when no return
    path was provided.

    Args:
        redirect_path: The validated return path or custom scheme, or None.
        idp_name: Provider display name (included on success).
        success: Whether the link succeeded.

    Returns:
        The absolute URL (or custom-scheme URL) to redirect the browser to.
    """
    params = {"idp_link": "success" if success else "error"}
    if success and idp_name is not None:
        params["idp_name"] = idp_name
    if redirect_path and idp_utils.is_custom_scheme_redirect(redirect_path):
        return _append_query_params(redirect_path, params)
    base = redirect_path or "/settings/security"
    return f"{core_config.settings.ENDURAIN_HOST}{_append_query_params(base, params)}"


@router.get(
    "",
    response_model=list[idp_schema.IdentityProviderPublicRead],
)
def get_enabled_identity_providers(
    db: core_dependencies.DbSession,
    service: idp_dependencies.IdentityProviderService,
) -> list[idp_schema.IdentityProviderPublicRead]:
    """Retrieve a list of enabled identity providers from the database.

    Args:
        db (Session): SQLAlchemy database session dependency.
        service: Identity provider service.

    Returns:
        List[IdentityProviderPublic]: A list of enabled identity providers, each represented as an IdentityProviderPublic schema.
    """
    return service.get_enabled_identity_providers(db)


@router.get("/login/{idp_slug}", status_code=status.HTTP_307_TEMPORARY_REDIRECT, response_class=RedirectResponse)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def initiate_login(
    idp_slug: auth_dependencies.IdentityProviderSlug,
    request: Request,
    db: core_dependencies.DbSession,
    service: idp_dependencies.IdentityProviderService,
    code_challenge: Annotated[
        str,
        Query(
            description="PKCE code challenge (base64url-encoded SHA256, 43-128 chars). REQUIRED for OAuth 2.1 compliance.",
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
        HTTPException: If the identity provider is not found, disabled, or PKCE validation fails.
    """
    try:
        # Get the identity provider
        idp = service.get_identity_provider_by_slug(idp_slug, db)
        if not idp or not idp.enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity provider not found or disabled",
            )

        # PKCE is REQUIRED for all clients (OAuth 2.1 compliance)
        if not code_challenge:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_challenge is required (PKCE mandatory for all clients)",
            )
        if not code_challenge_method or code_challenge_method != "S256":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="code_challenge_method must be S256",
            )

        # Validate PKCE challenge format
        auth_computation.validate_pkce_challenge(code_challenge, code_challenge_method)

        # Validate redirect URL to prevent open redirect vulnerability
        idp_utils.validate_redirect_url(redirect, core_config.settings.ALLOWED_REDIRECT_SCHEMES)

        # Preserve mobile intent for custom-scheme redirects.
        # The browser step of the flow cannot reliably carry X-Client-Type,
        # so the validated redirect target is the authoritative signal for
        # mobile handoff flows such as Gadgetbridge.
        if idp_utils.is_custom_scheme_redirect(redirect):
            client_type = "mobile"
        else:
            client_type = request.headers.get("X-Client-Type", "web")
            if client_type not in ["web", "mobile"]:
                client_type = "web"  # Default to web if invalid

        # Create and store OAuth state in database (replaces cookie-based state)
        state_id = service.create_login_oauth_state(
            idp.id,
            client_type=client_type,
            ip_address=core_network.get_ip_address(request),
            redirect_path=redirect,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            db=db,
        )

        service.log_public_flow_event(
            "debug",
            "OAuth state created: <state_id> for IdP <slug> (client_type=<client_type>)",
            extra=core_logger.context(state_id=state_id, slug=idp.slug, client_type=client_type),
        )

        # Initiate the OAuth flow with database state ID (no cookies)
        authorization_url = service.initiate_login(idp, db, redirect, oauth_state_id=state_id)

        return RedirectResponse(url=authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    except HTTPException:
        raise
    except Exception as err:
        service.log_public_flow_event(
            "error", "Error in initiate_login: <err>", exc_info=err, extra=core_logger.context(err=err)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate login",
        ) from err


@router.get("/callback/{idp_slug}", status_code=status.HTTP_307_TEMPORARY_REDIRECT, response_class=RedirectResponse)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def handle_callback(
    request: Request,
    response: Response,
    idp_slug: auth_dependencies.IdentityProviderSlug,
    password_hasher: Annotated[
        credentials_integration.PasswordHasher,
        Depends(credentials_integration.get_password_hasher),
    ],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
    db: core_dependencies.DbSession,
    service: idp_dependencies.IdentityProviderService,
    code: str = Query(..., description="Authorization code from IdP"),
    state: str = Query(..., description="State parameter for CSRF protection"),
):
    """Handle OAuth callback from an identity provider.

    This endpoint processes the OAuth authorization callback from external identity providers.
    It supports two modes: login mode (default) and link mode (for linking IdP to existing account).

    Args:
        idp_slug (str): The slug identifier of the identity provider.
        password_hasher (credentials_integration.PasswordHasher): Password hasher dependency for session management.
        token_manager (access_tokens_integration.TokenManager): Token manager dependency for creating session tokens.
        db (Session): Database session dependency.
        code (str): Authorization code received from the identity provider.
        state (str): State parameter used for CSRF protection (database state ID).
        request (Request): The incoming HTTP request.
        response: Response that receives the cookies.
        service: Identity provider service.

    Returns:
        RedirectResponse: A redirect response to either:
            - Settings page (link mode): /settings with success parameters
            - Login page (login mode): /login with session_id for token exchange
            - Error page: /login with error parameter if callback fails

    Raises:
        HTTPException: If the identity provider is not found, disabled, or if callback processing fails.

    Notes:
        - In link mode: Redirects to settings without creating a new session
        - In login mode: Creates session, redirects with session_id (client must exchange for tokens)
        - All clients must call /tokens exchange endpoint with PKCE verifier to get JWT tokens
        - On error: Redirects to login page with error parameter
        - All redirects use HTTP 307 (Temporary Redirect) status code
    """
    oauth_state = None
    try:
        # Get the identity provider
        idp = service.get_identity_provider_by_slug(idp_slug, db)
        if not idp or not idp.enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity provider not found or disabled",
            )

        # Lookup OAuth state from database (mandatory for all clients)
        oauth_state = service.get_unused_oauth_state(state, db)

        if not oauth_state:
            service.log_public_flow_event(
                "warning",
                "OAuth state not found in database: <value_1>",
                extra=core_logger.context(value_1=core_hashing.log_fingerprint(state)),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OAuth state",
            )

        # Bind the OAuth state to the IdP named in the callback URL.
        # The `idp` is resolved from the URL slug while the `oauth_state`
        # is looked up by the opaque `state` parameter; without this check
        # a state minted during one provider's login could be replayed
        # against a different provider's callback. Cross-provider misuse is
        # already blocked cryptographically (the code is exchanged at the
        # URL-IdP's token endpoint and the ID token is verified against that
        # IdP's JWKS), but asserting the binding here fails fast and protects
        # deployments where two IdP entries share an authorization server.
        if oauth_state.idp_id is not None and oauth_state.idp_id != idp.id:
            service.log_public_flow_event(
                "warning",
                "OAuth state IdP mismatch for state <value_1>: state.idp_id=<idp_id>, callback idp.id=<id>",
                extra=core_logger.context(
                    value_1=core_hashing.log_fingerprint(state), idp_id=oauth_state.idp_id, id=idp.id
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OAuth state",
            )

        # Mark state as used atomically (prevents replay attacks).
        # Two concurrent callbacks can both reach this point with the same
        # `oauth_state` row in memory; only the caller whose conditional UPDATE
        # actually flips `used=False -> True` is allowed to continue. Losing
        # races (replays, double-submits) abort here with a generic 400 so we
        # do not leak whether the state existed but was already consumed.
        if not service.claim_oauth_state(state, db):
            service.log_public_flow_event(
                "warning",
                "OAuth state replay/race rejected: <value_1>",
                extra=core_logger.context(value_1=core_hashing.log_fingerprint(state)),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OAuth state",
            )

        service.log_public_flow_event(
            "debug",
            "OAuth callback received for state <value_1> (client_type=<client_type>)",
            extra=core_logger.context(value_1=core_hashing.log_fingerprint(state), client_type=oauth_state.client_type),
        )

        # Process the OAuth callback (service will handle both DB and cookie state)
        result = service.handle_callback(idp, code, state, password_hasher, oauth_state, db)

        user = result["user"]
        is_link_mode = result.get("mode") == "link"

        # Handle link mode differently - redirect to the originating page (the
        # caller's validated return path) without creating a new session.
        if is_link_mode:
            redirect_url = _build_link_result_url(oauth_state.redirect_path, idp.name, success=True)

            service.log_public_flow_event(
                "info",
                "IdP link successful for user <username>, IdP <name>",
                extra=core_logger.context(username=user.username, name=idp.name),
            )

            return RedirectResponse(
                url=redirect_url,
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )

        # LOGIN MODE: Create a session without tokens; token exchange supplies them after PKCE.
        session_id = service.create_callback_session(user, request, password_hasher, oauth_state.id, db)

        # Redirect to frontend with session_id for token exchange
        frontend_url = core_config.settings.ENDURAIN_HOST
        redirect_url = f"{frontend_url}/login?sso=success&session_id={session_id}"

        redirect_path = result.get("redirect_path")
        if redirect_path:
            # Encoded so a "&" or "#" in the path cannot start another query parameter;
            # "/" and ":" stay readable and the frontend decodes the value back.
            redirect_url += f"&redirect={quote(redirect_path, safe='/:')}"
            # Signal the frontend that this is a custom-scheme redirect.
            # The frontend will skip its own token exchange and instead
            # pass the session_id to the mobile app via the custom scheme.
            is_custom_scheme = "://" in redirect_path and not redirect_path.startswith("http")
            if is_custom_scheme:
                redirect_url += "&external_redirect=true"

        # The session ID is the handle exchanged for tokens, so only a one-way
        # fingerprint is logged: enough to correlate with other entries, useless to replay.
        service.log_public_flow_event(
            "info",
            "SSO login successful for user <username> via <name> (session=<value_3>)",
            extra=core_logger.context(
                username=user.username, name=idp.name, value_3=core_hashing.log_fingerprint(session_id)
            ),
        )

        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    except HTTPException:
        raise
    except Exception as err:
        service.log_public_flow_event(
            "error", "Error in SSO callback: <err>", exc_info=err, extra=core_logger.context(err=err)
        )

        # A failed LINK returns the browser to its originating page with an error
        # flag; a failed LOGIN falls back to the login page. Link attempts are
        # identified by the user_id stored on the OAuth state at initiation.
        if oauth_state is not None and oauth_state.user_id is not None:
            error_url = _build_link_result_url(oauth_state.redirect_path, None, success=False)
        else:
            error_url = f"{core_config.settings.ENDURAIN_HOST}/login?error=sso_failed"

        return RedirectResponse(url=error_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
