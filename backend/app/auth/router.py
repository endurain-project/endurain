from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import auth._internal.internal_dependencies as auth_internal_dependencies
import auth._internal.password_hasher as auth_password_hasher
import auth._internal.security_stores as auth_security_stores
import auth._internal.token_manager as auth_token_manager
import auth.identity_providers.utils as idp_utils
import auth.identity_service as auth_identity_service
import auth.mfa.service as mfa_service
import auth.schema as auth_schema
import auth.sessions.crud as auth_sessions_crud
import auth.sessions.rotated_refresh_tokens.utils as auth_sessions_rotated_tokens_utils
import auth.sessions.utils as auth_sessions_utils
import auth.utils as auth_utils
import core.database as core_database
import core.logger as core_logger
import core.rate_limit as core_rate_limit
import users.users.crud as users_crud
import users.users.utils as users_utils

# Define the API router
router = APIRouter()


def _validate_pkce_query_params(
    client_type: str,
    code_challenge: str | None,
    code_challenge_method: str | None,
) -> None:
    """
    Reject malformed PKCE query-parameter combinations.

    Args:
        client_type: Client type supplied by the caller.
        code_challenge: Optional PKCE code challenge.
        code_challenge_method: Optional PKCE challenge method.

    Returns:
        None.

    Raises:
        HTTPException: If PKCE parameters are supplied partially.
    """
    if client_type != "mobile":
        return

    has_any_pkce_param = code_challenge is not None or code_challenge_method is not None
    has_complete_pkce_params = bool(code_challenge and code_challenge_method)

    if has_any_pkce_param and not has_complete_pkce_params:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("code_challenge and code_challenge_method must be provided together"),
        )


def _raise_auth_security_store_unavailable(
    err: auth_security_stores.AuthSecurityStoreUnavailableError,
) -> None:
    """
    Return a controlled response when auth security storage is down.

    Args:
        err: Auth security storage outage.

    Returns:
        None.

    Raises:
        HTTPException: Always raised with a 503 status.
    """
    core_logger.print_to_log(
        "Auth security storage unavailable during authentication",
        "error",
        exc=err,
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication temporarily unavailable",
    ) from err


@router.post(
    "/login",
    response_model=(
        auth_schema.MFARequiredResponse
        | auth_schema.MobileSessionResponse
        | auth_schema.TokenResponseWeb
        | auth_schema.TokenResponseMobile
    ),
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
async def login_for_access_token(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    client_type: Annotated[str, Depends(auth_internal_dependencies.header_client_type_scheme)],
    failed_attempts: Annotated[
        auth_security_stores.FailedLoginStore,
        Depends(auth_security_stores.get_failed_login_attempts),
    ],
    pending_mfa_store: Annotated[
        auth_security_stores.PendingMFAStore,
        Depends(auth_security_stores.get_pending_mfa_store),
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    code_challenge: Annotated[str | None, Query()] = None,
    code_challenge_method: Annotated[str | None, Query()] = None,
):
    """
    Handles user login and access token generation, including Multi-Factor Authentication (MFA) flow.

    Protection Mechanisms:
    - Rate limiting: 10 requests per minute per IP (SENSITIVE tier, prevents DoS attacks)
    - Progressive lockout: Per-username tracking prevents targeted brute-force:
      * 5 failures: 5 minute lockout
      * 10 failures: 30 minute lockout
      * 20 failures: 24 hour lockout

    This endpoint authenticates a user using provided credentials, checks if the user is active,
    and determines if MFA is required. If MFA is enabled for the user, it stores the pending login
    and returns an MFA-required response. Otherwise, it completes the login process and returns
    the required information.

    PKCE Support (Mobile):
    - Mobile clients can optionally provide code_challenge and code_challenge_method
    - For mobile clients with PKCE parameters, tokens are not returned directly
        - Instead, a session_id is returned for secure token exchange via
            /public/idp/session/{session_id}/tokens

    Args:
        response: The HTTP response object
        request: The HTTP request object
        form_data: Form data containing username and password
        client_type: The type of client making the request ("web" or "mobile")
        failed_attempts: Failed login attempts tracker for progressive lockout
        pending_mfa_store: Store for pending MFA logins
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        code_challenge: PKCE code challenge (base64url-encoded SHA256, optional for mobile)
        code_challenge_method: PKCE method (must be S256 if provided, optional for mobile)

    Returns:
        Union[auth_schema.MFARequiredResponse, dict, str]:
            - If MFA is required, returns an MFA-required response (schema or dict depending on client type)
            - If MFA is not required and mobile client with PKCE, returns session_id for token exchange
            - If MFA is not required and no PKCE, proceeds with normal login via auth_utils.complete_login()

    Raises:
        HTTPException: If authentication fails, user is inactive, or account is locked
    """
    _validate_pkce_query_params(
        client_type,
        code_challenge,
        code_challenge_method,
    )

    # Check if username is locked out from too many failed login attempts
    try:
        if failed_attempts.is_locked_out(form_data.username):
            lockout_until = failed_attempts.get_lockout_time(form_data.username)
            if lockout_until:
                seconds_remaining = int((lockout_until - datetime.now(UTC)).total_seconds())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Account locked due to too many failed login attempts. Try again in {seconds_remaining} seconds.",
                )
    except auth_security_stores.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)

    # Authenticate user
    try:
        user = auth_utils.authenticate_user(form_data.username, form_data.password, password_hasher, db)
    except HTTPException as err:
        # Record failed attempt on authentication errors (401 Unauthorized)
        if err.status_code == 401:
            try:
                failed_attempts.record_failed_attempt(form_data.username)
            except auth_security_stores.AuthSecurityStoreUnavailableError as store_err:
                _raise_auth_security_store_unavailable(store_err)
        raise err

    # Check if the user is active
    users_utils.check_user_is_active(user)

    # Check if MFA is enabled for this user
    if mfa_service.is_mfa_enabled_for_user(user.id, db):
        # Store the user for pending MFA verification
        try:
            pending_mfa_store.add_pending_login(form_data.username, user.id)
        except auth_security_stores.AuthSecurityStoreUnavailableError as err:
            _raise_auth_security_store_unavailable(err)

        # Don't reset failed login attempts yet - wait for MFA verification
        # This prevents bypassing lockout by triggering MFA flow

        # Return MFA required response
        if client_type == "web":
            response.status_code = status.HTTP_202_ACCEPTED
            return auth_schema.MFARequiredResponse(
                mfa_required=True,
                username=form_data.username,
                message="MFA verification required",
            )
        if client_type == "mobile":
            return {
                "mfa_required": True,
                "username": form_data.username,
                "message": "MFA verification required",
            }

    # Password authentication successful and no MFA required
    # Reset failed login attempts counter
    try:
        failed_attempts.reset_attempts(form_data.username)
    except auth_security_stores.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)

    # Mobile clients with PKCE use secure token exchange flow
    # Web clients don't need PKCE - they have httpOnly cookies and same-origin protection
    if client_type == "mobile" and code_challenge and code_challenge_method:
        # Use PKCE exchange flow through the public IdP token exchange endpoint
        return auth_utils.create_mobile_pkce_session_response(
            response,
            request,
            user,
            code_challenge,
            code_challenge_method,
            password_hasher,
            db,
        )

    # Web clients and mobile without PKCE get tokens directly
    return auth_utils.complete_login(response, request, user, client_type, password_hasher, token_manager, db)


@router.post(
    "/mfa/verify",
    response_model=(auth_schema.MobileSessionResponse | auth_schema.TokenResponseWeb | auth_schema.TokenResponseMobile),
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
async def verify_mfa_and_login(
    response: Response,
    request: Request,
    mfa_request: auth_schema.MFALoginRequest,
    client_type: Annotated[str, Depends(auth_internal_dependencies.header_client_type_scheme)],
    failed_attempts: Annotated[
        auth_security_stores.FailedLoginStore,
        Depends(auth_security_stores.get_failed_login_attempts),
    ],
    pending_mfa_store: Annotated[
        auth_security_stores.PendingMFAStore,
        Depends(auth_security_stores.get_pending_mfa_store),
    ],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    code_challenge: Annotated[str | None, Query()] = None,
    code_challenge_method: Annotated[str | None, Query()] = None,
):
    """
    Verify MFA code and complete login process.

    This endpoint verifies the MFA code for a pending login and completes
    the authentication process if the code is valid.

    PKCE Support (Mobile):
    - Mobile clients can optionally provide code_challenge and code_challenge_method
    - For mobile clients with PKCE parameters, tokens are not returned directly
        - Instead, a session_id is returned for secure token exchange via
            /public/idp/session/{session_id}/tokens

    Args:
        response: The HTTP response object
        request: The HTTP request object
        failed_attempts: Failed login attempts tracker for progressive lockout
        mfa_request: MFA login request containing username and MFA code
        client_type: The type of client making the request ("web" or "mobile")
        pending_mfa_store: Store for pending MFA logins
        identity_service: Identity service used to verify backup codes.
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        code_challenge: PKCE code challenge (base64url-encoded SHA256, optional for mobile)
        code_challenge_method: PKCE method (must be S256 if provided, optional for mobile)

    Returns:
        Result from auth_utils.complete_login() or PKCE session response

    Raises:
        HTTPException: If no pending login found, MFA code is invalid, or user not found
    """
    _validate_pkce_query_params(
        client_type,
        code_challenge,
        code_challenge_method,
    )

    username_log_id = auth_security_stores.username_log_identifier(mfa_request.username)

    # Check if user is locked out from too many failed attempts
    try:
        if pending_mfa_store.is_locked_out(mfa_request.username):
            lockout_until = pending_mfa_store.get_lockout_time(mfa_request.username)
            if lockout_until:
                seconds_remaining = int((lockout_until - datetime.now(UTC)).total_seconds())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many failed MFA attempts. Account locked for {seconds_remaining} seconds.",
                )
    except auth_security_stores.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)

    # Check if there's a pending MFA login for this username
    try:
        user_id = pending_mfa_store.get_pending_login(mfa_request.username)
    except auth_security_stores.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)
    if not user_id:
        # Run a dummy Argon2 verify so the wall-clock latency of the
        # "no pending MFA login" branch matches the "pending login,
        # wrong code" branch (where backup-code verification performs
        # an Argon2 verify). Without this, an attacker could enumerate
        # which usernames are mid-login by measuring response time.
        password_hasher.dummy_verify()
        core_logger.print_to_log(
            f"No pending MFA login found for {username_log_id}",
            "warning",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending MFA login found for this username",
        )

    # Verify the MFA code (TOTP or backup code)
    if not mfa_service.verify_user_mfa(user_id, mfa_request.mfa_code, identity_service, db):
        # Record failed attempt and apply lockout if threshold exceeded
        try:
            failed_count = pending_mfa_store.record_failed_attempt(mfa_request.username)
        except auth_security_stores.AuthSecurityStoreUnavailableError as err:
            _raise_auth_security_store_unavailable(err)
        core_logger.print_to_log(
            f"Invalid MFA code for {username_log_id}. Failed attempts: {failed_count}",
            "warning",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code, backup code or backup code already used.",
        )

    try:
        claimed_user_id = pending_mfa_store.claim_pending_login(mfa_request.username)
    except auth_security_stores.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)
    if claimed_user_id != user_id:
        core_logger.print_to_log(
            f"Pending MFA login for {username_log_id} was missing or already claimed",
            "warning",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending MFA login found for this username",
        )

    # Get the user and complete login
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        core_logger.print_to_log(f"User ID {user_id} not found during MFA verification", "warning")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to authenticate",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if the user is still active
    users_utils.check_user_is_active(user)

    # MFA verification successful - reset both MFA and login failed attempts counters
    try:
        pending_mfa_store.reset_attempts(mfa_request.username)
        failed_attempts.reset_attempts(mfa_request.username)
    except auth_security_stores.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)

    # Mobile clients with PKCE use secure token exchange flow
    # Web clients don't need PKCE - they have httpOnly cookies and same-origin protection
    if client_type == "mobile" and code_challenge and code_challenge_method:
        # Use PKCE exchange flow through the public IdP token exchange endpoint
        return auth_utils.create_mobile_pkce_session_response(
            response,
            request,
            user,
            code_challenge,
            code_challenge_method,
            password_hasher,
            db,
        )

    # Web clients and mobile without PKCE get tokens directly
    return auth_utils.complete_login(response, request, user, client_type, password_hasher, token_manager, db)


@router.post(
    "/refresh",
    response_model=(auth_schema.TokenResponseWeb | auth_schema.TokenResponseMobile),
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
async def refresh_token(
    response: Response,
    request: Request,
    _validate_refresh_token: Annotated[Callable, Depends(auth_internal_dependencies.validate_refresh_token)],
    token_user_id: Annotated[
        int,
        Depends(auth_internal_dependencies.get_sub_from_refresh_token),
    ],
    token_session_id: Annotated[
        str,
        Depends(auth_internal_dependencies.get_sid_from_refresh_token),
    ],
    refresh_token_value: Annotated[
        str,
        Depends(auth_internal_dependencies.get_and_return_refresh_token),
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    client_type: Annotated[str, Depends(auth_internal_dependencies.header_client_type_scheme)],
    x_csrf_token: Annotated[str | None, Depends(auth_internal_dependencies.header_csrf_token_scheme)] = None,
):
    """
    Handles the refresh token process for user sessions.

    This endpoint validates the provided refresh token, checks session status,
    validates the CSRF token (web clients only), and issues new tokens.

    OAuth 2.1 Bootstrap Pattern for Page Reload:
        On page reload, in-memory tokens are lost but httpOnly cookie persists.
        - If no CSRF header: Allow refresh (page reload scenario)
        - If CSRF header provided: Validate it (legitimate request with cached token)
        - Security: httpOnly cookie + SameSite=Strict prevents CSRF at browser level
        - CSRF validation adds defense-in-depth but is not the primary protection

    Args:
        response: The HTTP response object.
        request: The HTTP request object.
        _validate_refresh_token: Dependency to validate the refresh token.
        token_user_id: User ID extracted from the refresh token.
        token_session_id: Session ID extracted from the refresh token.
        refresh_token_value: The raw refresh token value.
        password_hasher: Utility for verifying token hashes.
        token_manager: Utility for creating tokens.
        db: Database session.
        client_type: Client type (\"web\" or \"mobile\").
        x_csrf_token: CSRF token header (web clients only, optional on page reload).

    Returns:
        dict: Contains session_id, access_token, csrf_token, token_type, expires_in, refresh_token_expires_in.

    Raises:
        HTTPException: If session not found, refresh token invalid,
                       user is inactive, or CSRF token is invalid (when provided).
    """
    # Get the session from the database
    session = auth_sessions_crud.get_session_by_id_not_expired(token_session_id, db)

    # Check if the session was found
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Defense-in-depth: ensure the session belongs to the user named in
    # the refresh token's `sub` claim. The refresh-token hash stored on
    # the session is already bound to this user, so a mismatched token
    # would fail hash verification below — but asserting ownership here
    # makes the invariant explicit and fails fast (rather than relying on
    # the implicit binding) if a token's `sub`/`sid` claims are ever
    # decoupled from the persisted session.
    if session.user_id != token_user_id:
        core_logger.print_to_log(
            f"Refresh token session owner mismatch: token sub={token_user_id}, session user_id={session.user_id}",
            "warning",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate session hasn't exceeded idle or absolute timeout
    auth_sessions_utils.validate_session_timeout(session)

    # Verify CSRF token for web clients only
    # Mobile clients don't use CSRF tokens
    # OAuth 2.1 Bootstrap Pattern for page reload:
    # - On EVERY page reload, in-memory tokens (incl. CSRF) are lost but the
    #   httpOnly refresh cookie persists. The client therefore POSTs to
    #   /refresh without an X-CSRF-Token header to bootstrap a new in-memory
    #   token. This must continue to work even after a CSRF binding has been
    #   minted on the session, otherwise the user is logged out on reload.
    # - When the client DOES send a header, it MUST be valid. An empty/wrong
    #   value is rejected (prevents partial-CSRF where script can read the
    #   cookie but not the bound token).
    # - CSRF protection at this endpoint is defense-in-depth; the primary
    #   protections are HttpOnly + SameSite=Strict on the refresh cookie,
    #   which prevent a cross-site attacker from issuing this POST at all.
    if (
        client_type == "web"
        and x_csrf_token
        and session.csrf_token_hash is not None
        and not auth_sessions_utils.verify_csrf_token(x_csrf_token, session.csrf_token_hash)
    ):
        # CSRF token was provided: validate it
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify session has a refresh token (not pending PKCE exchange)
    if not session.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tokens not yet exchanged via PKCE. Complete SSO/PKCE flow first.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check for token reuse BEFORE validating token
    # Uses HMAC-SHA256 internally for deterministic, secure lookup
    is_reused, in_grace = auth_sessions_rotated_tokens_utils.check_token_reuse(refresh_token_value, db)

    if is_reused and not in_grace:
        # Token theft detected - invalidate entire family
        auth_sessions_rotated_tokens_utils.invalidate_token_family(session.token_family_id, db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected. All sessions invalidated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if is_reused and in_grace:
        # Idempotent in-grace replay. The presented refresh token was already
        # rotated, but we are still inside the grace window, so this is a
        # legitimate retry: a lost rotation response, or a racing/duplicate
        # refresh from a background uploader. The presented token no longer
        # matches the session's current refresh-token hash, so instead of a
        # 401 we replay the exact replacement minted on the original rotation.
        # The session is NOT re-rotated (no new rotated record, no
        # rotation_count bump), so duplicate/concurrent refreshes converge.
        replay = auth_sessions_rotated_tokens_utils.get_grace_replay_token(refresh_token_value, db)

        if replay is None:
            # Replacement was cleaned up (or never stored); fall back to the
            # standard invalid-token response.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        replay_refresh_token, replay_refresh_token_exp = replay

        # Validate the user is still present and active before re-issuing.
        replay_user = users_crud.get_user_by_id(token_user_id, db)

        if replay_user is None:
            core_logger.print_to_log(
                f"User ID {token_user_id} not found during token refresh replay",
                "warning",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to authenticate",
                headers={"WWW-Authenticate": "Bearer"},
            )

        users_utils.check_user_is_active(replay_user)

        # Mint a fresh, stateless access token (safe to re-issue every retry).
        replay_access_token_exp, replay_access_token = auth_utils.mint_access_token(
            replay_user, token_manager, session.id
        )

        # Web clients lost their CSRF token along with the rotation response, so
        # mint a fresh one and bind it to the session (the refresh token itself
        # is unchanged). Mobile clients do not use CSRF.
        replay_csrf_token: str | None = None
        if client_type == "web":
            replay_csrf_token = token_manager.create_csrf_token()
            auth_sessions_utils.update_session_csrf_token(session.id, replay_csrf_token, db)

        return auth_utils.build_token_response(
            response,
            client_type,
            session.id,
            replay_access_token,
            replay_access_token_exp,
            replay_refresh_token,
            replay_refresh_token_exp,
            replay_csrf_token,
        )

    is_valid = password_hasher.verify_password(refresh_token_value, session.refresh_token)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # get user
    user = users_crud.get_user_by_id(token_user_id, db)

    if user is None:
        core_logger.print_to_log(f"User ID {token_user_id} not found during token refresh", "warning")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to authenticate",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if the user is active
    users_utils.check_user_is_active(user)

    # Create the new token bundle first so the rotated record can persist the
    # replacement refresh token used for idempotent in-grace replay.
    (
        session_id,
        new_access_token_exp,
        new_access_token,
        new_refresh_token_exp,
        new_refresh_token,
        new_csrf_token,
    ) = auth_utils.create_tokens(user, token_manager, session.id)

    # Store the rotated (old) refresh token together with the encrypted
    # replacement so a retry within the grace window can replay it.
    # store_rotated_token hashes the old token with HMAC-SHA256 for lookup
    # and encrypts the replacement at rest.
    auth_sessions_rotated_tokens_utils.store_rotated_token(
        refresh_token_value,
        session.token_family_id,
        session.rotation_count,
        db,
        replacement_refresh_token=new_refresh_token,
        replacement_refresh_token_exp=new_refresh_token_exp,
    )

    # Edit session and store in database
    # Note: edit_session automatically increments rotation_count
    # and updates last_rotation_at
    auth_sessions_utils.edit_session(
        session,
        request,
        new_refresh_token,
        password_hasher,
        db,
        new_csrf_token=new_csrf_token,
    )

    # Opportunistically refresh IdP tokens for all linked identity providers
    await idp_utils.refresh_idp_tokens_if_needed(user.id, db)

    # Token delivery based on client type (web cookie vs mobile body) is
    # centralised in auth_utils.build_token_response so login, /refresh, and
    # SSO token exchange share one delivery contract.
    return auth_utils.build_token_response(
        response,
        client_type,
        session_id,
        new_access_token,
        new_access_token_exp,
        new_refresh_token,
        new_refresh_token_exp,
        new_csrf_token,
    )


@router.post("/logout", response_model=auth_schema.LogoutResponse)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
async def logout(
    response: Response,
    request: Request,
    _validate_refresh_token: Annotated[Callable, Depends(auth_internal_dependencies.validate_refresh_token)],
    token_session_id: Annotated[
        str,
        Depends(auth_internal_dependencies.get_sid_from_refresh_token),
    ],
    refresh_token_value: Annotated[
        str,
        Depends(auth_internal_dependencies.get_and_return_refresh_token),
    ],
    client_type: Annotated[str, Depends(auth_internal_dependencies.header_client_type_scheme)],
    token_user_id: Annotated[
        int,
        Depends(auth_internal_dependencies.get_sub_from_refresh_token),
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Log out a user by validating and deleting their session.

    Args:
        response: The HTTP response object to modify cookies.
        request: The HTTP request object.
        _validate_refresh_token: Dependency to validate the refresh token.
        token_session_id: The session ID extracted from the refresh token.
        refresh_token_value: The refresh token value from the request.
        client_type: The type of client ("web" or "mobile").
        token_user_id: The user ID extracted from the refresh token.
        password_hasher: Utility for verifying the refresh token.
        db: Database session for CRUD operations.

    Returns:
        dict: A message indicating successful logout.

    Raises:
        HTTPException: If refresh token is invalid (401 Unauthorized).
        HTTPException: If client type is invalid (403 Forbidden).
    """
    # Get the session from the database
    session = auth_sessions_crud.get_session_by_id_not_expired(token_session_id, db)

    # Check if the session was found
    if session is not None:
        # Verify session has a refresh token (not pending PKCE exchange)
        if not session.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tokens not yet exchanged via PKCE. Cannot logout incomplete session.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Verify the refresh token
        is_valid = password_hasher.verify_password(refresh_token_value, session.refresh_token)

        # If the refresh token is not valid, raise an exception
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Delete the session from the database
        auth_sessions_crud.delete_session(session.id, token_user_id, db)

        # Clear all IdP refresh tokens for security
        await idp_utils.clear_all_idp_tokens(token_user_id, db)

    if client_type == "web":
        auth_utils.clear_refresh_token_cookies(response)
        return {"message": "Logout successful"}
    if client_type == "mobile":
        return {"message": "Logout successful"}
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid client type",
        headers={"WWW-Authenticate": "Bearer"},
    )
