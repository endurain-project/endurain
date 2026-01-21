from typing import Annotated, List
from datetime import datetime, timezone, timedelta
import secrets
from uuid import uuid4
import os
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import core.database as core_database
import core.rate_limit as core_rate_limit
import auth.password_hasher as auth_password_hasher
import auth.token_manager as auth_token_manager
import auth.utils as auth_utils
import auth.constants as auth_constants
import users.users_sessions.utils as users_session_utils
import users.users_sessions.crud as users_session_crud
import auth.identity_providers.crud as idp_crud
import auth.identity_providers.schema as idp_schema
import auth.identity_providers.service as idp_service
import auth.identity_providers.utils as idp_utils
import users.users.schema as users_schema
import core.config as core_config
import core.logger as core_logger
import auth.oauth_state.crud as oauth_state_crud


# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=List[idp_schema.IdentityProviderPublic],
    status_code=status.HTTP_200_OK,
)
async def get_enabled_providers(db: Annotated[Session, Depends(core_database.get_db)]):
    """
    Retrieve a list of enabled identity providers from the database.

    Args:
        db (Session): SQLAlchemy database session dependency.

    Returns:
        List[IdentityProviderPublic]: A list of enabled identity providers, each represented as an IdentityProviderPublic schema.
    """
    providers = idp_crud.get_enabled_providers(db)
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
@core_rate_limit.limiter.limit(core_rate_limit.OAUTH_AUTHORIZE_LIMIT)
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

        # Detect client type from X-Client-Type header
        client_type = request.headers.get("X-Client-Type", "web")
        if client_type not in ["web", "mobile"]:
            client_type = "web"  # Default to web if invalid

        # Generate OAuth state and nonce
        state_id = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)

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

        core_logger.print_to_log(
            f"OAuth state created: {state_id} for IdP {idp.slug} (client_type={client_type})",
            "debug",
        )

        # Initiate the OAuth flow with database state ID (no cookies)
        authorization_url = await idp_service.idp_service.initiate_login(
            idp, request, db, redirect, oauth_state_id=state_id
        )

        return RedirectResponse(
            url=authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(f"Error in initiate_login: {err}", "error", exc=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate login",
        ) from err


@router.get("/callback/{idp_slug}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
@core_rate_limit.limiter.limit(core_rate_limit.OAUTH_CALLBACK_LIMIT)
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
            core_logger.print_to_log(
                f"OAuth state not found in database: {state[:8]}...",
                "warning",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OAuth state",
            )

        # Mark state as used atomically (prevents replay attacks)
        oauth_state_crud.mark_oauth_state_used(db, state)

        core_logger.print_to_log(
            f"OAuth callback received for state {state[:8]}... (client_type={oauth_state.client_type})",
            "debug",
        )

        # Process the OAuth callback (service will handle both DB and cookie state)
        result = await idp_service.idp_service.handle_callback(
            idp, code, state, request, password_hasher, db, oauth_state
        )

        user = result["user"]
        is_link_mode = result.get("mode") == "link"

        # Handle link mode differently - redirect to settings without creating new session
        if is_link_mode:
            frontend_url = core_config.ENDURAIN_HOST
            redirect_url = f"{frontend_url}/settings?tab=security&idp_link=success&idp_name={idp.name}"

            core_logger.print_to_log(
                f"IdP link successful for user {user.username}, IdP {idp.name}", "info"
            )

            return RedirectResponse(
                url=redirect_url,
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )

        # LOGIN MODE: Create session WITHOUT tokens (tokens created during exchange)
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

        users_session_utils.create_session(
            session_id,
            user_read,
            request,
            None,
            password_hasher,
            db,
            oauth_state_id=oauth_state.id,
        )

        # Redirect to frontend with session_id for token exchange
        frontend_url = core_config.ENDURAIN_HOST
        redirect_url = f"{frontend_url}/login?sso=success&session_id={session_id}"

        redirect_path = result.get("redirect_path")
        if redirect_path:
            redirect_url += f"&redirect={redirect_path}"

        core_logger.print_to_log(
            f"SSO login successful for user {user.username} via {idp.name} (session_id={session_id})",
            "info",
        )

        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(f"Error in SSO callback: {err}", "error", exc=err)

        # Redirect to frontend with error
        frontend_url = core_config.ENDURAIN_HOST
        error_url = f"{frontend_url}/login?error=sso_failed"

        return RedirectResponse(
            url=error_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )


@router.post(
    "/session/{session_id}/tokens",
    response_model=idp_schema.TokenExchangeResponse,
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.PKCE_TOKEN_EXCHANGE_LIMIT)
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
    Exchange PKCE code_verifier for JWT tokens (mobile SSO flow).

    After OAuth callback completes and creates a session, mobile clients must
    call this endpoint to prove they possess the code_verifier (PKCE) and
    receive the actual JWT tokens. This prevents token leakage through browser
    redirects and ensures only the legitimate client can access the tokens.

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
        session_with_state = users_session_crud.get_session_with_oauth_state(
            session_id, db
        )

        if not session_with_state:
            core_logger.print_to_log(
                f"Token exchange failed: session {session_id[:8]}... not found",
                "warning",
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or not eligible for token exchange",
            )

        session_obj, oauth_state = session_with_state

        # Verify session is linked to an OAuth state (mobile flow)
        if not oauth_state:
            core_logger.print_to_log(
                f"Token exchange failed: session {session_id[:8]}... has no OAuth state",
                "warning",
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not created via mobile SSO flow",
            )

        # Check if tokens have already been exchanged (prevent replay)
        if session_obj.tokens_exchanged:
            core_logger.print_to_log(
                f"Token exchange replay attempt for session {session_id[:8]}...",
                "warning",
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tokens already exchanged for this session",
            )

        # Verify PKCE code_verifier matches code_challenge
        if not oauth_state.code_challenge or not oauth_state.code_challenge_method:
            core_logger.print_to_log(
                f"Token exchange failed: OAuth state {oauth_state.id[:8]}... missing PKCE data",
                "error",
            )
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

        # PKCE verification successful - retrieve user and create tokens
        user = session_obj.users
        user_read = users_schema.UsersRead.model_validate(user)

        # Create JWT tokens (now that PKCE is verified)
        (
            _,
            access_token_exp,
            access_token,
            _,
            refresh_token,
            csrf_token,
        ) = auth_utils.create_tokens(user_read, token_manager, session_id)

        # Calculate expires_in from access token expiration
        expires_in = int(
            (access_token_exp - datetime.now(timezone.utc)).total_seconds()
        )

        # Update session with the actual hashed refresh token
        # Note: csrf_token_hash is NOT stored here (OAuth 2.1 bootstrap pattern).
        # The first /refresh call after page reload establishes the CSRF binding.
        session_obj.refresh_token = password_hasher.hash_password(refresh_token)
        db.commit()

        # Store client_type before marking tokens as exchanged (which deletes oauth_state)
        client_type = oauth_state.client_type

        # Set refresh token cookie for web clients (enables logout)
        if client_type == "web":
            secure = os.environ.get("FRONTEND_PROTOCOL") == "https"
            response.set_cookie(
                key="endurain_refresh_token",
                value=refresh_token,
                expires=datetime.now(timezone.utc)
                + timedelta(days=auth_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
                httponly=True,
                path="/",
                secure=secure,
                samesite="strict",
            )

        # Mark tokens as exchanged to prevent replay attacks
        users_session_crud.mark_tokens_exchanged(session_id, db)

        core_logger.print_to_log(
            f"Token exchange successful for session {session_id[:8]}... (user={user.username}, client_type={client_type})",
            "info",
        )

        # Return response based on client type (matches complete_login behavior)
        if client_type == "web":
            # Web: access_token and csrf_token in body, refresh_token in cookie only
            return idp_schema.TokenExchangeResponse(
                session_id=session_id,
                access_token=access_token,
                csrf_token=csrf_token,
                expires_in=expires_in,
                token_type="Bearer",
            )
        else:
            # Mobile: all tokens in body (no cookies)
            return idp_schema.TokenExchangeResponse(
                session_id=session_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
                token_type="Bearer",
            )

    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"Error in token exchange for session {session_id[:8]}...: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to exchange tokens",
        ) from err
