"""Public (unauthenticated) HTTP routes for identity provider SSO flows."""

from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import core.rate_limit as core_rate_limit
import modules.auth._internal.password_hasher as auth_password_hasher
import modules.auth._internal.token_manager as auth_token_manager
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.identity_providers.service as idp_service
import modules.auth.identity_providers.utils as idp_utils
import modules.auth.oauth_state.crud as oauth_state_crud
import modules.auth.oauth_state.utils as oauth_state_utils
import modules.auth.sessions.crud as auth_sessions_crud
import modules.auth.sessions.utils as auth_sessions_utils
import modules.auth.utils as auth_utils
import modules.users.users.schema as users_schema
import modules.users.users.utils as users_utils

logger = core_logger.get_logger(__name__)

# Define the API router
router = APIRouter()


def _append_query_params(url: str, params: dict[str, str]) -> str:
    """Append query parameters to a URL or relative path, preserving any existing query."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _build_link_result_url(redirect_path: str | None, idp_name: str | None, *, success: bool) -> str:
    """
    Build the post-link redirect that carries the result to the originating client.

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
    response_model=list[idp_schema.IdentityProviderPublic],
    status_code=status.HTTP_200_OK,
)
async def get_enabled_identity_providers(db: Annotated[Session, Depends(core_database.get_db)]):
    """
    Retrieve a list of enabled identity providers from the database.

    Args:
        db (Session): SQLAlchemy database session dependency.

    Returns:
        List[IdentityProviderPublic]: A list of enabled identity providers, each represented as an IdentityProviderPublic schema.
    """
    providers = idp_crud.get_enabled_identity_providers(db)
    return [
        idp_schema.IdentityProviderPublic(
            id=p.id,
            name=p.name,
            slug=p.slug,
            icon=p.icon,
        )
        for p in providers
    ]


@router.get("/login/{idp_slug}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
async def initiate_login(
    idp_slug: str,
    request: Request,
    db: Annotated[Session, Depends(core_database.get_db)],
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
    """
    Initiates the login process for a given identity provider using OAuth.

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
        idp = idp_crud.get_identity_provider_by_slug(idp_slug, db)
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
        idp_utils.validate_pkce_challenge(code_challenge, code_challenge_method)

        # Validate redirect URL to prevent open redirect vulnerability
        idp_utils.validate_redirect_url(redirect)

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

        # Generate OAuth state and nonce
        state_id, nonce = oauth_state_utils.create_state_id_and_nonce()

        # Get client IP address
        client_ip = request.client.host if request.client else None

        # Create and store OAuth state in database (replaces cookie-based state)
        oauth_state_crud.create_oauth_state(
            db=db,
            state_id=state_id,
            idp_id=idp.id,
            nonce=nonce,
            client_type=client_type,
            ip_address=client_ip,
            redirect_path=redirect,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )

        logger.debug(f"OAuth state created: {state_id} for IdP {idp.slug} (client_type={client_type})")

        # Initiate the OAuth flow with database state ID (no cookies)
        authorization_url = await idp_service.idp_service.initiate_login(
            idp, request, db, redirect, oauth_state_id=state_id
        )

        return RedirectResponse(url=authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Error in initiate_login: {err}", exc_info=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate login",
        ) from err


@router.get("/callback/{idp_slug}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
async def handle_callback(
    request: Request,
    response: Response,
    idp_slug: str,
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    code: str = Query(..., description="Authorization code from IdP"),
    state: str = Query(..., description="State parameter for CSRF protection"),
):
    """
    Handle OAuth callback from an identity provider.

    This endpoint processes the OAuth authorization callback from external identity providers.
    It supports two modes: login mode (default) and link mode (for linking IdP to existing account).
    Args:
        idp_slug (str): The slug identifier of the identity provider.
        password_hasher (auth_password_hasher.PasswordHasher): Password hasher dependency for session management.
        token_manager (auth_token_manager.TokenManager): Token manager dependency for creating session tokens.
        db (Session): Database session dependency.
        code (str): Authorization code received from the identity provider.
        state (str): State parameter used for CSRF protection (database state ID).
        request (Request): The incoming HTTP request.

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
        idp = idp_crud.get_identity_provider_by_slug(idp_slug, db)
        if not idp or not idp.enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity provider not found or disabled",
            )

        # Lookup OAuth state from database (mandatory for all clients)
        oauth_state = oauth_state_crud.get_oauth_state_by_id_and_not_used(state, db)

        if not oauth_state:
            logger.warning(f"OAuth state not found in database: {state[:8]}...")
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
            logger.warning(
                f"OAuth state IdP mismatch for state {state[:8]}...: "
                f"state.idp_id={oauth_state.idp_id}, callback idp.id={idp.id}"
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
        if not oauth_state_crud.mark_oauth_state_used(state, db):
            logger.warning(f"OAuth state replay/race rejected: {state[:8]}...")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OAuth state",
            )

        logger.debug(f"OAuth callback received for state {state[:8]}... (client_type={oauth_state.client_type})")

        # Process the OAuth callback (service will handle both DB and cookie state)
        result = await idp_service.idp_service.handle_callback(
            idp, code, state, request, password_hasher, db, oauth_state
        )

        user = result["user"]
        is_link_mode = result.get("mode") == "link"

        # Handle link mode differently - redirect to the originating page (the
        # caller's validated return path) without creating a new session.
        if is_link_mode:
            redirect_url = _build_link_result_url(oauth_state.redirect_path, idp.name, success=True)

            logger.info(f"IdP link successful for user {user.username}, IdP {idp.name}")

            return RedirectResponse(
                url=redirect_url,
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )

        # LOGIN MODE: Create session WITHOUT tokens (tokens created during exchange)
        # Validate that the user is active before creating a session
        users_utils.check_user_is_active(user)

        # Convert to UsersRead schema
        user_read = users_schema.UsersRead.model_validate(user)

        # Generate session ID
        session_id = str(uuid4())

        # Create the session and store it in the database
        if not oauth_state:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth state required for token exchange",
            )

        auth_sessions_utils.create_session(
            session_id,
            user_read,
            request,
            None,
            password_hasher,
            db,
            oauth_state_id=oauth_state.id,
        )

        # Redirect to frontend with session_id for token exchange
        frontend_url = core_config.settings.ENDURAIN_HOST
        redirect_url = f"{frontend_url}/login?sso=success&session_id={session_id}"

        redirect_path = result.get("redirect_path")
        if redirect_path:
            redirect_url += f"&redirect={redirect_path}"
            # Signal the frontend that this is a custom-scheme redirect.
            # The frontend will skip its own token exchange and instead
            # pass the session_id to the mobile app via the custom scheme.
            is_custom_scheme = "://" in redirect_path and not redirect_path.startswith("http")
            if is_custom_scheme:
                redirect_url += "&external_redirect=true"

        logger.info(f"SSO login successful for user {user.username} via {idp.name} (session_id={session_id})")

        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Error in SSO callback: {err}", exc_info=err)

        # A failed LINK returns the browser to its originating page with an error
        # flag; a failed LOGIN falls back to the login page. Link attempts are
        # identified by the user_id stored on the OAuth state at initiation.
        if oauth_state is not None and oauth_state.user_id is not None:
            error_url = _build_link_result_url(oauth_state.redirect_path, None, success=False)
        else:
            error_url = f"{core_config.settings.ENDURAIN_HOST}/login?error=sso_failed"

        return RedirectResponse(url=error_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.post(
    "/session/{session_id}/tokens",
    response_model=idp_schema.TokenExchangeResponse,
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
async def exchange_tokens_for_session(
    session_id: str,
    request: Request,
    response: Response,
    token_exchange: idp_schema.TokenExchangeRequest,
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Exchange a PKCE code verifier for JWT tokens.

    After OAuth callback or password PKCE login creates a session, clients
    call this endpoint to prove they possess the code_verifier (PKCE) and
    receive the actual JWT tokens. This prevents token leakage through
    browser redirects and ensures only the legitimate client can access the
    tokens.

    Security Features:
    - PKCE verification (SHA256 hash of verifier must match challenge)
    - One-time exchange (tokens_exchanged flag prevents replay)
    - Rate limited (10 requests/minute)
    - Session must be linked to OAuth state with PKCE data

    Rate Limit: 10 requests per minute per IP

    Args:
        session_id (str): Session ID from OAuth callback redirect.
        request (Request): FastAPI request object (for rate limiting).
        response (Response): FastAPI response object.
        token_exchange (TokenExchangeRequest): Request body with code_verifier.
        token_manager (TokenManager): Token manager dependency.
        db (Session): Database session dependency.

    Returns:
        TokenExchangeResponse: JWT tokens (access, refresh, csrf) and metadata.

    Raises:
        HTTPException:
            - 404 NOT_FOUND: Session not found or not linked to OAuth state
            - 400 BAD_REQUEST: Invalid code_verifier or tokens already exchanged
            - 409 CONFLICT: Tokens already exchanged for this session
    """
    try:
        # Retrieve session with OAuth state relationship
        session_with_state = auth_sessions_crud.get_session_with_oauth_state(session_id, db)

        if not session_with_state:
            logger.warning(f"Token exchange failed: session {session_id[:8]}... not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or not eligible for token exchange",
            )

        session_obj, oauth_state = session_with_state

        # Verify session is linked to an OAuth state (mobile flow)
        if not oauth_state:
            logger.warning(f"Token exchange failed: session {session_id[:8]}... has no OAuth state")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not eligible for PKCE token exchange",
            )

        # Check if tokens have already been exchanged (prevent replay).
        # This is a fast-path informational check; the authoritative
        # protection is the atomic conditional UPDATE below, which
        # closes a TOCTOU race that two concurrent exchanges with the
        # same code_verifier would otherwise win.
        if session_obj.tokens_exchanged:
            logger.warning(f"Token exchange replay attempt for session {session_id[:8]}...")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tokens already exchanged for this session",
            )

        # Verify PKCE code_verifier matches code_challenge
        if not oauth_state.code_challenge or not oauth_state.code_challenge_method:
            logger.error(f"Token exchange failed: OAuth state {oauth_state.id[:8]}... missing PKCE data")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAuth state missing PKCE data",
            )

        # Validate code_verifier and verify it matches the challenge
        idp_utils.validate_pkce_verifier(
            code_verifier=token_exchange.code_verifier,
            code_challenge=oauth_state.code_challenge,
            code_challenge_method=oauth_state.code_challenge_method,
        )

        # Determine client_type for this token exchange before minting
        # tokens or claiming the one-shot session. A mismatched
        # X-Client-Type must not be able to burn an otherwise valid
        # PKCE session by flipping tokens_exchanged first.
        #
        # Authority order:
        #   1. ``oauth_state.client_type`` — set when the IdP flow was
        #      initiated by an authenticated client that DID send
        #      ``X-Client-Type``. When this is non-None it represents
        #      the original, server-recorded intent and the exchange
        #      caller MUST NOT override it.
        #   2. ``X-Client-Type`` header on the exchange request —
        #      only consulted when ``oauth_state.client_type`` is None,
        #      which is the genuine system-browser case (the OS
        #      browser carries no custom headers when opening
        #      ``/initiate_login``, so the original intent could not
        #      be recorded).
        #
        # Previously the header was preferred unconditionally
        # (`request.headers.get("X-Client-Type", stored or "web")`),
        # which let the exchange caller switch between the
        # cookie-set ``web`` shape and the body-only ``mobile`` shape
        # at will — bypassing the cookie-set decision and the
        # response shape that should follow from how the flow was
        # actually initiated.
        stored_client_type = oauth_state.client_type
        header_client_type = request.headers.get("X-Client-Type")
        if header_client_type not in ("web", "mobile"):
            header_client_type = None

        if stored_client_type in ("web", "mobile"):
            # Recorded intent wins. If the caller declared a
            # different value, reject the exchange — this is either
            # a misbehaving client or an attacker trying to flip the
            # response shape. We do NOT silently downgrade.
            if header_client_type is not None and header_client_type != stored_client_type:
                logger.warning(
                    "Token exchange client_type mismatch for session "
                    f"{session_id[:8]}...: stored={stored_client_type}, "
                    f"header={header_client_type}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="client_type does not match the OAuth state",
                )
            client_type = stored_client_type
        else:
            # Genuine system-browser flow — fall back to the header,
            # defaulting to ``web`` when the header is absent.
            client_type = header_client_type or "web"

        # PKCE verification successful - retrieve user and create tokens
        user = session_obj.users
        # Validate that the user is still active before minting tokens
        users_utils.check_user_is_active(user)
        user_read = users_schema.UsersRead.model_validate(user)

        # Create JWT tokens (now that PKCE is verified)
        (
            _,
            access_token_exp,
            access_token,
            refresh_token_exp,
            refresh_token,
            csrf_token,
        ) = auth_utils.create_tokens(user_read, token_manager, session_id)

        # Calculate expires_in from access token expiration
        expires_in = int((access_token_exp - datetime.now(UTC)).total_seconds())

        # Calculate refresh_token_expires_in from refresh token expiration
        refresh_token_expires_in = int((refresh_token_exp - datetime.now(UTC)).total_seconds())

        # Update session with the actual hashed refresh token AND
        # mark tokens as exchanged in a single atomic conditional
        # UPDATE. This closes the check-then-act race where two
        # concurrent exchanges with the correct verifier could both
        # pass the ``tokens_exchanged`` guard, both mint refresh
        # tokens, and the second overwrite the first — handing the
        # second caller a working refresh token while invalidating
        # the first.
        # Note: csrf_token_hash is NOT stored here (OAuth 2.1
        # bootstrap pattern). The first /refresh call after page
        # reload establishes the CSRF binding.
        claimed = auth_sessions_crud.claim_session_for_token_exchange(
            session_id,
            password_hasher.hash_password(refresh_token),
            db,
        )
        if not claimed:
            logger.warning(f"Token exchange lost race for session {session_id[:8]}...")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tokens already exchanged for this session",
            )

        # Set refresh token cookie for web clients (enables logout).
        # Cookie attributes (Secure, SameSite, Path, expiry) are
        # centralised in auth_utils.set_refresh_token_cookie so this
        # SSO flow stays in lockstep with password login and /refresh
        # — previously this site used FRONTEND_PROTOCOL and could
        # issue a non-Secure refresh cookie when that env var was
        # missing or mis-set in production.
        if client_type == "web":
            auth_utils.set_refresh_token_cookie(response, refresh_token)

        # Note: tokens_exchanged was flipped atomically together
        # with the refresh-token hash above, so no second write is
        # needed here. The atomic claim also detached the OAuth
        # state row for cleanup.

        logger.info(
            f"Token exchange successful for session {session_id[:8]}... (user={user.username}, client_type={client_type})"
        )

        # Return response based on client type (matches complete_login behavior)
        if client_type == "web":
            # Web: access_token and csrf_token in body, refresh_token in cookie only
            return idp_schema.TokenExchangeResponse(
                session_id=session_id,
                access_token=access_token,
                csrf_token=csrf_token,
                expires_in=expires_in,
                refresh_token_expires_in=refresh_token_expires_in,
                token_type="Bearer",
            )
        else:
            # Mobile: all tokens in body (no cookies)
            return idp_schema.TokenExchangeResponse(
                session_id=session_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
                refresh_token_expires_in=refresh_token_expires_in,
                token_type="Bearer",
            )

    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Error in token exchange for session {session_id[:8]}...: {err}", exc_info=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to exchange tokens",
        ) from err
