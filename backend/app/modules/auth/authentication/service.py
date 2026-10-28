"""Authentication workflows for login and token delivery."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import (
    Request,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.network as core_network
import modules.auth.access_tokens.integration_service as auth_token_manager
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.security_stores as auth_security_stores
import modules.auth.computation as auth_computation
import modules.auth.credentials.integration_service as auth_credentials_crud
import modules.auth.credentials.integration_service as auth_password_hasher
import modules.auth.mfa.dependencies as mfa_dependencies
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.oauth_state.integration_service as oauth_state_crud
import modules.auth.rotated_refresh_tokens.integration_service as auth_sessions_rotated_tokens_utils
import modules.auth.sessions.integration_service as auth_sessions_integration
import modules.auth.sessions.integration_service as auth_sessions_utils
import modules.server_settings.contracts as server_settings_contracts
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def authenticate_user(
    username: str,
    password: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
) -> users_schema.UsersRead:
    """Authenticates a user by verifying the provided username and password.

    Args:
        username (str): The username of the user attempting to authenticate.
        password (str): The plaintext password provided by the user.
        password_hasher (auth_password_hasher.PasswordHasher): An instance of the password hasher for verifying and updating password hashes.
        db (Session): The database session used for querying and updating user data.

    Returns:
        users_schema.UsersRead: The authenticated user object if authentication is successful.

    Raises:
        HTTPException: If the username does not exist or the password is invalid.
    """
    # Get the user from the database
    user = users_integration.get_user_by_username(username, db)

    # Check if the user exists and if the password is correct
    if not user:
        # Run a dummy Argon2 verify so that the wall-clock latency of
        # the "user not found" branch matches the "user found, wrong
        # password" branch. Without this, Argon2's deliberately-tuned
        # ~hundreds-of-milliseconds verify time is trivially observable
        # from the network and lets an attacker enumerate valid
        # usernames without ever tripping FailedLoginAttempts (lockout
        # is only recorded on 401, which the attacker does not care
        # about while probing existence).
        password_hasher.dummy_verify()
        raise core_exceptions.UnauthenticatedError("Unable to authenticate with provided credentials", scheme="Bearer")

    # Load the user's local password hash from the auth-owned credential
    # table. A missing row means the account has no local password.
    credential = auth_credentials_crud.get_credential(user.id, db)
    stored_hash = credential.password_hash if credential is not None else None

    # User has no local password (SSO-only account). Treat identically
    # to "wrong password" so neither the response body nor the timing
    # discloses the account's auth modality. The dummy verify keeps
    # the latency consistent with a normal Argon2 verify.
    if stored_hash is None:
        password_hasher.dummy_verify()
        raise core_exceptions.UnauthenticatedError("Unable to authenticate with provided credentials", scheme="Bearer")

    # Verify password and get updated hash if applicable
    is_password_valid, updated_hash = password_hasher.verify_and_update(password, stored_hash)
    if not is_password_valid:
        raise core_exceptions.UnauthenticatedError("Unable to authenticate with provided credentials", scheme="Bearer")

    # Update user hash if applicable
    if updated_hash:
        auth_credentials_crud.set_local_password_hash(user.id, updated_hash, db)

    # Return the user if the password is correct
    return user


def create_tokens(
    user: users_schema.UsersRead,
    token_manager: auth_token_manager.TokenManager,
    policy: server_settings_contracts.SessionPolicy,
    session_id: str | None = None,
) -> tuple[str, datetime, str, datetime, str, str]:
    """Generates session tokens for a user, including access token, refresh token, and CSRF token.

    Args:
        user (users_schema.UsersRead): The user object for whom the tokens are being created.
        token_manager (auth_token_manager.TokenManager): The token manager responsible for token creation.
        policy (server_settings_contracts.SessionPolicy): The token lifetimes to apply.
        session_id (str | None, optional): An optional session ID. If not provided, a new unique session ID is generated.

    Returns:
        tuple[str, datetime, str, datetime, str, str]:
            A tuple containing:
                - session_id (str): The session identifier.
                - access_token_exp (datetime): Expiration datetime of the access token.
                - access_token (str): The access token string.
                - refresh_token_exp (datetime): Expiration datetime of the refresh token.
                - refresh_token (str): The refresh token string.
                - csrf_token (str): The CSRF token string.
    """
    if session_id is None:
        # Generate a unique session ID
        session_id = str(uuid4())

    # Create the access, refresh tokens and csrf token
    access_token_exp, access_token = token_manager.create_token(
        session_id, user, auth_token_manager.TokenType.ACCESS, policy.access_token_ttl
    )

    refresh_token_exp, refresh_token = token_manager.create_token(
        session_id, user, auth_token_manager.TokenType.REFRESH, policy.refresh_token_ttl
    )

    csrf_token = token_manager.create_csrf_token()

    return (
        session_id,
        access_token_exp,
        access_token,
        refresh_token_exp,
        refresh_token,
        csrf_token,
    )


def mint_access_token(
    user: users_schema.UsersRead,
    token_manager: auth_token_manager.TokenManager,
    session_id: str,
    policy: server_settings_contracts.SessionPolicy,
) -> tuple[datetime, str]:
    """Mint a single fresh access token for an existing session.

    Used by the in-grace refresh replay path, which keeps the
    existing (replayed) refresh token but still needs to hand the
    client a new, full-lifetime access token.

    Args:
        user: The user the token is issued for.
        token_manager: Token manager responsible for token creation.
        session_id: Existing session identifier to bind the token to.
        policy: The token lifetimes to apply.

    Returns:
        Tuple of (access_token_exp, access_token).
    """
    return token_manager.create_token(session_id, user, auth_token_manager.TokenType.ACCESS, policy.access_token_ttl)


def build_token_response(
    response: Response,
    client_type: str,
    session_id: str,
    access_token: str,
    access_token_exp: datetime,
    refresh_token: str,
    refresh_token_exp: datetime,
    csrf_token: str,
) -> dict:
    """Build the OAuth 2.1 token-response body for login and refresh.

    Single source of truth for token delivery, shared by the password
    login, SSO login, and ``/refresh`` flows so they cannot drift:

    - Web clients receive the refresh token as an ``HttpOnly`` cookie
      (set here via :func:`set_refresh_token_cookie`) and the CSRF token
      in the body.
    - Mobile clients receive the refresh token in the body and no CSRF
      token.

    ``expires_in`` / ``refresh_token_expires_in`` are seconds-until-expiry
    per RFC 6749 §5.1.

    Args:
        response: HTTP response used to set the web refresh cookie.
        client_type: ``"web"`` or any other value (treated as mobile).
        session_id: Session identifier.
        access_token: Newly minted access token.
        access_token_exp: Access-token expiry datetime.
        refresh_token: Newly minted refresh token.
        refresh_token_exp: Refresh-token expiry datetime.
        csrf_token: CSRF token (only returned to web clients).

    Returns:
        dict: Response body for the client type.

    Raises:
        None.
    """
    now = datetime.now(UTC)
    body = {
        "session_id": session_id,
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": int((access_token_exp - now).total_seconds()),
        "refresh_token_expires_in": int((refresh_token_exp - now).total_seconds()),
    }

    if client_type == "web":
        # Web: Refresh token as httpOnly cookie (XSS protection); CSRF
        # token in body for in-memory storage. Cookie attributes are
        # centralised in set_refresh_token_cookie so login, /refresh, and
        # SSO token exchange stay in lockstep.
        authentication_dependencies.set_refresh_token_cookie(
            response,
            refresh_token,
            refresh_token_exp,
            environment=core_config.settings.ENVIRONMENT,
        )
        body["csrf_token"] = csrf_token
    else:
        # Mobile: All tokens in JSON body for secure platform storage.
        body["refresh_token"] = refresh_token

    return body


def complete_login(
    response: Response,
    request: Request,
    user: users_schema.UsersRead,
    client_type: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    token_manager: auth_token_manager.TokenManager,
    db: Session,
) -> dict:
    """Handles the completion of the login process by generating session and authentication tokens,.

    storing the session in the database, and returning tokens in response body.

    OAuth 2.1 compliant: Returns tokens in response body for all clients.
    - Access token and CSRF token: Returned in body (for in-memory storage)
    - Refresh token: Set as httpOnly cookie with SameSite=Strict

    This unified model works for both username/password and SSO login flows.

    Args:
        response (Response): The HTTP response object to set refresh cookie.
        request (Request): The HTTP request object containing client information.
        user (users_schema.UsersRead): The authenticated user object.
        client_type (str): The type of client ("web" or "mobile").
        password_hasher (auth_password_hasher.PasswordHasher): Utility for password hashing.
        token_manager (auth_token_manager.TokenManager): Utility for token generation and management.
        db (Session): Database session for storing session information.

    Returns:
        dict: Contains session_id, access_token, csrf_token, token_type, expires_in, and refresh_token_expires_in.

    Raises:
        HTTPException: If the client type is invalid, raises a 403 Forbidden error.
    """
    if client_type not in ["web", "mobile"]:
        logger.warning("Login refused for an unsupported client type")
        raise core_exceptions.PermissionDeniedError("Invalid client type")

    # Create the tokens
    (
        session_id,
        access_token_exp,
        access_token,
        refresh_token_exp,
        refresh_token,
        csrf_token,
    ) = create_tokens(user, token_manager, server_settings_integration.get_session_policy(db))

    # Create the session and store it in the database
    # Note: csrf_token is NOT stored on initial login (csrf_token_hash = None).
    # This enables the OAuth 2.1 bootstrap pattern where the first /refresh call
    # after page reload establishes the CSRF binding. The httpOnly cookie is
    # sufficient authentication for the bootstrap refresh.
    auth_sessions_utils.create_session(
        session_id,
        user,
        request,
        refresh_token,
        password_hasher,
        refresh_token_exp,
        db,
    )

    # Token delivery based on client type (web cookie vs mobile body) is
    # centralised in build_token_response so login, /refresh, and SSO
    # token exchange share one delivery contract.
    return build_token_response(
        response,
        client_type,
        session_id,
        access_token,
        access_token_exp,
        refresh_token,
        refresh_token_exp,
        csrf_token,
    )


def create_mobile_pkce_session_response(
    response: Response,
    request: Request,
    user: users_schema.UsersRead,
    code_challenge: str,
    code_challenge_method: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
) -> auth_schema.MobileSessionResponse:
    """Create a session for mobile password login with PKCE exchange flow.

    This function is exclusively for mobile clients. Web clients should use
    complete_login() which provides secure token delivery via httpOnly cookies.

    Similar to SSO flow, but for password authentication.
    Returns session_id instead of tokens—tokens obtained via
    POST /public/idp/session/{session_id}/tokens with code_verifier.

    Args:
        response: FastAPI response object
        request: FastAPI request object
        user: Authenticated user object
        code_challenge: PKCE code challenge (base64url-encoded SHA256)
        code_challenge_method: PKCE method (must be S256)
        password_hasher: Password hasher instance
        db: Database session

    Returns:
        auth_schema.MobileSessionResponse: Contains session_id and mfa_required flag

    Raises:
        HTTPException: If PKCE parameters are invalid

    Notes:
        - Mobile-only: Web clients use complete_login() with httpOnly cookies
        - Session created without tokens (pending exchange)
        - OAuth state record stores PKCE challenge
        - Client must POST to /public/idp/session/{session_id}/tokens
        - Reuses existing token exchange endpoint from SSO flow
    """
    # Validate PKCE challenge format
    if code_challenge_method != "S256":
        raise core_exceptions.InvalidInputError("Only S256 PKCE method is supported")

    auth_computation.validate_pkce_challenge(code_challenge, code_challenge_method)

    # Generate session ID
    session_id = str(uuid4())

    # Create OAuth state record for PKCE (reuse SSO infrastructure)
    state_id, nonce = oauth_state_crud.create_state_id_and_nonce()
    client_ip = core_network.get_ip_address(request)

    oauth_state_crud.create_oauth_state(
        db=db,
        state_id=state_id,
        nonce=nonce,
        client_type="mobile",  # This function is mobile-only
        ip_address=client_ip,
        redirect_path=None,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    # Create session linked to oauth_state (enables PKCE exchange)
    auth_sessions_utils.create_session(
        session_id,
        user,
        request,
        None,  # No refresh token yet
        password_hasher,
        datetime.now(UTC) + server_settings_integration.get_session_policy(db).refresh_token_ttl,
        db,
        oauth_state_id=state_id,
    )

    # Return session_id for token exchange (no tokens yet)
    return auth_schema.MobileSessionResponse(
        session_id=session_id,
        mfa_required=False,
        message=("Complete authentication by exchanging tokens at /public/idp/session/{session_id}/tokens"),
    )


def _validate_pkce_query_params(
    client_type: str,
    code_challenge: str | None,
    code_challenge_method: str | None,
) -> None:
    """Reject malformed PKCE query-parameter combinations.

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
        raise core_exceptions.InvalidInputError("code_challenge and code_challenge_method must be provided together")


def _raise_auth_security_store_unavailable(
    err: auth_security_stores.AuthSecurityStoreUnavailableError,
) -> None:
    """Return a controlled response when auth security storage is down.

    Args:
        err: Auth security storage outage.

    Returns:
        None.

    Raises:
        HTTPException: Always raised with a 503 status.
    """
    logger.error("Auth security storage unavailable during authentication", exc_info=err)
    raise core_exceptions.ServiceUnavailableError("Authentication temporarily unavailable")


def login_for_access_token(
    response: Response,
    request: Request,
    form_data: OAuth2PasswordRequestForm,
    client_type: str,
    failed_attempts: failed_login_store.FailedLoginStore,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    password_hasher: auth_password_hasher.PasswordHasher,
    token_manager: auth_token_manager.TokenManager,
    db: Session,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
):
    """Handles user login and access token generation, including Multi-Factor Authentication (MFA) flow.

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
            - If MFA is not required and no PKCE, proceeds with normal login via complete_login()

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
                raise core_exceptions.TooManyRequestsError(
                    f"Account locked due to too many failed login attempts. Try again in {seconds_remaining} seconds."
                )
    except auth_security_stores.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)

    # Authenticate user
    try:
        user = authenticate_user(form_data.username, form_data.password, password_hasher, db)
    except core_exceptions.UnauthenticatedError as err:
        # Record failed attempt on authentication errors (401 Unauthorized)
        if err.status_code == 401:
            try:
                failed_attempts.record_failed_attempt(form_data.username)
            except auth_security_stores.AuthSecurityStoreUnavailableError as store_err:
                _raise_auth_security_store_unavailable(store_err)
        raise err

    # Check if the user is active
    users_integration.require_active_user(user)

    # Check if MFA is enabled for this user
    if mfa_integration.is_mfa_enabled_for_user(user.id, db):
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
        return create_mobile_pkce_session_response(
            response,
            request,
            user,
            code_challenge,
            code_challenge_method,
            password_hasher,
            db,
        )

    # Web clients and mobile without PKCE get tokens directly
    return complete_login(response, request, user, client_type, password_hasher, token_manager, db)


def verify_mfa_and_login(
    response: Response,
    request: Request,
    mfa_request: auth_schema.MFALoginRequest,
    client_type: str,
    failed_attempts: failed_login_store.FailedLoginStore,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    password_hasher: auth_password_hasher.PasswordHasher,
    token_manager: auth_token_manager.TokenManager,
    db: Session,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
):
    """Verify MFA code and complete login process.

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
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        code_challenge: PKCE code challenge (base64url-encoded SHA256, optional for mobile)
        code_challenge_method: PKCE method (must be S256 if provided, optional for mobile)

    Returns:
        Result from complete_login() or PKCE session response

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
                raise core_exceptions.TooManyRequestsError(
                    f"Too many failed MFA attempts. Account locked for {seconds_remaining} seconds."
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
        logger.warning(
            "No pending MFA login found for <username_log_id>",
            extra=core_logger.context(username_log_id=username_log_id),
        )
        raise core_exceptions.InvalidInputError("No pending MFA login found for this username")

    # Verify the MFA code (TOTP or backup code)
    if not mfa_integration.verify_user_mfa(user_id, mfa_request.mfa_code, auth_credentials_crud, db):
        # Record failed attempt and apply lockout if threshold exceeded
        try:
            failed_count = pending_mfa_store.record_failed_attempt(mfa_request.username)
        except auth_security_stores.AuthSecurityStoreUnavailableError as err:
            _raise_auth_security_store_unavailable(err)
        logger.warning(
            "Invalid MFA code for <username_log_id>. Failed attempts: <failed_count>",
            extra=core_logger.context(username_log_id=username_log_id, failed_count=failed_count),
        )
        raise core_exceptions.InvalidInputError("Invalid MFA code, backup code or backup code already used.")

    try:
        claimed_user_id = pending_mfa_store.claim_pending_login(mfa_request.username)
    except auth_security_stores.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)
    if claimed_user_id != user_id:
        logger.warning(
            "Pending MFA login for <username_log_id> was missing or already claimed",
            extra=core_logger.context(username_log_id=username_log_id),
        )
        raise core_exceptions.InvalidInputError("No pending MFA login found for this username")

    # Get the user and complete login
    user = users_integration.get_user(user_id, db)
    if not user:
        logger.warning(
            "User ID <user_id> not found during MFA verification", extra=core_logger.context(user_id=user_id)
        )
        raise core_exceptions.UnauthenticatedError("Unable to authenticate", scheme="Bearer")

    # Check if the user is still active
    users_integration.require_active_user(user)

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
        return create_mobile_pkce_session_response(
            response,
            request,
            user,
            code_challenge,
            code_challenge_method,
            password_hasher,
            db,
        )

    # Web clients and mobile without PKCE get tokens directly
    return complete_login(response, request, user, client_type, password_hasher, token_manager, db)


def refresh_token(
    response: Response,
    request: Request,
    _validate_refresh_token: Callable,
    token_user_id: int,
    token_session_id: str,
    refresh_token_value: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    token_manager: auth_token_manager.TokenManager,
    client_type: str,
    db: Session,
    refresh_idp_tokens_if_needed: Callable[[int, Session], None] | None = None,
    x_csrf_token: str | None = None,
):
    r"""Handles the refresh token process for user sessions.

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

        refresh_idp_tokens_if_needed: Value used by this operation.

    Returns:
        dict: Contains session_id, access_token, csrf_token, token_type, expires_in, refresh_token_expires_in.

    Raises:
        HTTPException: If session not found, refresh token invalid,
                       user is inactive, or CSRF token is invalid (when provided).
    """
    # Get the session from the database
    session = auth_sessions_integration.get_session_by_id_not_expired(token_session_id, db)

    # Check if the session was found
    if session is None:
        raise core_exceptions.NotFoundError("Session not found")

    # Defense-in-depth: ensure the session belongs to the user named in
    # the refresh token's `sub` claim. The refresh-token hash stored on
    # the session is already bound to this user, so a mismatched token
    # would fail hash verification below — but asserting ownership here
    # makes the invariant explicit and fails fast (rather than relying on
    # the implicit binding) if a token's `sub`/`sid` claims are ever
    # decoupled from the persisted session.
    if session.user_id != token_user_id:
        logger.warning(
            "Refresh token session owner mismatch: token sub=<token_user_id>, session user_id=<user_id>",
            extra=core_logger.context(token_user_id=token_user_id, user_id=session.user_id),
        )
        raise core_exceptions.UnauthenticatedError("Invalid refresh token", scheme="Bearer")

    # Validate session hasn't exceeded idle or absolute timeout
    policy = server_settings_integration.get_session_policy(db)
    auth_sessions_integration.validate_session_timeout(session, policy)

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
        and not auth_sessions_integration.verify_csrf_token(x_csrf_token, session.csrf_token_hash)
    ):
        # CSRF token was provided: validate it
        raise core_exceptions.PermissionDeniedError("Invalid CSRF token")

    # Verify session has a refresh token (not pending PKCE exchange)
    if not session.refresh_token:
        raise core_exceptions.UnauthenticatedError(
            "Tokens not yet exchanged via PKCE. Complete SSO/PKCE flow first.", scheme="Bearer"
        )

    # Check for token reuse BEFORE validating token
    # Uses HMAC-SHA256 internally for deterministic, secure lookup
    is_reused, in_grace = auth_sessions_rotated_tokens_utils.check_token_reuse(refresh_token_value, db)

    if is_reused and not in_grace:
        # Token theft detected - invalidate entire family
        auth_sessions_integration.invalidate_token_family(session.token_family_id, db)
        raise core_exceptions.UnauthenticatedError("Token reuse detected. All sessions invalidated.", scheme="Bearer")

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
            raise core_exceptions.UnauthenticatedError("Invalid refresh token", scheme="Bearer")

        replay_refresh_token, replay_refresh_token_exp = replay

        # Validate the user is still present and active before re-issuing.
        replay_user = users_integration.get_user(token_user_id, db)

        if replay_user is None:
            logger.warning(
                "User ID <token_user_id> not found during token refresh replay",
                extra=core_logger.context(token_user_id=token_user_id),
            )
            raise core_exceptions.UnauthenticatedError("Unable to authenticate", scheme="Bearer")

        users_integration.require_active_user(replay_user)

        # Mint a fresh, stateless access token (safe to re-issue every retry).
        replay_access_token_exp, replay_access_token = mint_access_token(replay_user, token_manager, session.id, policy)

        # Web clients lost their CSRF token along with the rotation response, so
        # mint a fresh one and bind it to the session (the refresh token itself
        # is unchanged). Mobile clients do not use CSRF.
        replay_csrf_token: str | None = None
        if client_type == "web":
            replay_csrf_token = token_manager.create_csrf_token()
            auth_sessions_integration.update_session_csrf_token(session.id, replay_csrf_token, db)

        return build_token_response(
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
        raise core_exceptions.UnauthenticatedError("Invalid refresh token", scheme="Bearer")

    # get user
    user = users_integration.get_user(token_user_id, db)

    if user is None:
        logger.warning(
            "User ID <token_user_id> not found during token refresh",
            extra=core_logger.context(token_user_id=token_user_id),
        )
        raise core_exceptions.UnauthenticatedError("Unable to authenticate", scheme="Bearer")

    # Check if the user is active
    users_integration.require_active_user(user)

    # Create the new token bundle first so the rotated record can persist the
    # replacement refresh token used for idempotent in-grace replay.
    (
        session_id,
        new_access_token_exp,
        new_access_token,
        new_refresh_token_exp,
        new_refresh_token,
        new_csrf_token,
    ) = create_tokens(user, token_manager, policy, session.id)

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
    auth_sessions_integration.edit_session(
        session,
        request,
        new_refresh_token,
        password_hasher,
        new_refresh_token_exp,
        db,
        new_csrf_token=new_csrf_token,
    )

    # Opportunistically refresh IdP tokens for all linked identity providers
    if refresh_idp_tokens_if_needed is not None:
        refresh_idp_tokens_if_needed(user.id, db)

    # Token delivery based on client type (web cookie vs mobile body) is
    # centralised in build_token_response so login, /refresh, and
    # SSO token exchange share one delivery contract.
    return build_token_response(
        response,
        client_type,
        session_id,
        new_access_token,
        new_access_token_exp,
        new_refresh_token,
        new_refresh_token_exp,
        new_csrf_token,
    )


def logout(
    response: Response,
    request: Request,
    _validate_refresh_token: Callable,
    token_session_id: str,
    refresh_token_value: str,
    client_type: str,
    token_user_id: int,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
    clear_idp_tokens: Callable[[int, Session], None] | None = None,
):
    """Log out a user by validating and deleting their session.

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

        clear_idp_tokens: Value used by this operation.

    Returns:
        dict: A message indicating successful logout.

    Raises:
        HTTPException: If refresh token is invalid (401 Unauthorized).
        HTTPException: If client type is invalid (403 Forbidden).
    """
    # Get the session from the database
    session = auth_sessions_integration.get_session_by_id_not_expired(token_session_id, db)

    # Check if the session was found
    if session is not None:
        # Verify session has a refresh token (not pending PKCE exchange)
        if not session.refresh_token:
            raise core_exceptions.UnauthenticatedError(
                "Tokens not yet exchanged via PKCE. Cannot logout incomplete session.", scheme="Bearer"
            )

        # Verify the refresh token
        is_valid = password_hasher.verify_password(refresh_token_value, session.refresh_token)

        # If the refresh token is not valid, raise an exception
        if not is_valid:
            raise core_exceptions.UnauthenticatedError("Invalid refresh token", scheme="Bearer")

        # Delete the session from the database
        auth_sessions_integration.delete_session(session.id, token_user_id, db)

        # Clear all IdP refresh tokens for security
        if clear_idp_tokens is not None:
            clear_idp_tokens(token_user_id, db)

    if client_type == "web":
        authentication_dependencies.clear_refresh_token_cookies(response, environment=core_config.settings.ENVIRONMENT)
        return {"message": "Logout successful"}
    if client_type == "mobile":
        return {"message": "Logout successful"}
    logger.warning("Logout refused for an unsupported client type")
    raise core_exceptions.PermissionDeniedError("Invalid client type")
