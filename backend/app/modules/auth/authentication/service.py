"""Authentication workflows for login and token delivery."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import NoReturn
from uuid import uuid4

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.schema as auth_schema
import modules.auth.computation as auth_computation
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.integration_service as identity_providers_integration
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.mfa.dependencies as mfa_dependencies
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.rotated_refresh_tokens.integration_service as rotated_refresh_tokens_integration
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.contracts as server_settings_contracts
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


#: The one answer to an MFA step that fails, whether the code or the challenge was wrong.
_INVALID_MFA_CODE_MESSAGE = "Invalid MFA code, backup code or backup code already used."


def _refuse_credentials(username: str) -> NoReturn:
    """Log a refused sign-in and answer with the one message every cause shares.

    The account is named by a hashed identifier, so the log shows repeated guesses at one account without
    holding the username.

    Args:
        username: The username presented.

    Raises:
        UnauthenticatedError: Always.
    """
    logger.warning(
        "Sign-in refused for <username_log_id>",
        extra=core_logger.context(username_log_id=lockout_integration.username_log_identifier(username)),
    )
    raise core_exceptions.UnauthenticatedError("Unable to authenticate with provided credentials", scheme="Bearer")


def authenticate_user(
    username: str,
    password: str,
    password_hasher: credentials_integration.PasswordHasher,
    db: Session,
) -> users_schema.UsersRead:
    """Authenticates a user by verifying the provided username and password.

    Args:
        username (str): The username of the user attempting to authenticate.
        password (str): The plaintext password provided by the user.
        password_hasher (credentials_integration.PasswordHasher): An instance of the password hasher for verifying and updating password hashes.
        db (Session): The database session used for querying and updating user data.

    Returns:
        users_schema.UsersRead: The authenticated user object if authentication is successful.

    Raises:
        UnauthenticatedError: If the username does not exist or the password is invalid.
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
        _refuse_credentials(username)

    # Load the user's local password hash from the auth-owned credential
    # table. A missing row means the account has no local password.
    credential = credentials_integration.get_credential(user.id, db)
    stored_hash = credential.password_hash if credential is not None else None

    # User has no local password (SSO-only account). Treat identically
    # to "wrong password" so neither the response body nor the timing
    # discloses the account's auth modality. The dummy verify keeps
    # the latency consistent with a normal Argon2 verify.
    if stored_hash is None:
        password_hasher.dummy_verify()
        _refuse_credentials(username)

    # Verify password and get updated hash if applicable
    is_password_valid, updated_hash = password_hasher.verify_and_update(password, stored_hash)
    if not is_password_valid:
        _refuse_credentials(username)

    # Update user hash if applicable
    if updated_hash:
        credentials_integration.set_local_password_hash(user.id, updated_hash, db)

    # Return the user if the password is correct
    return user


def create_tokens(
    user: users_schema.UsersRead,
    token_manager: access_tokens_integration.TokenManager,
    policy: server_settings_contracts.SessionPolicy,
    session_id: str | None = None,
) -> tuple[str, datetime, str, datetime, str, str]:
    """Generates session tokens for a user, including access token, refresh token, and CSRF token.

    Args:
        user (users_schema.UsersRead): The user object for whom the tokens are being created.
        token_manager (access_tokens_integration.TokenManager): The token manager responsible for token creation.
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
        session_id, user, access_tokens_integration.TokenType.ACCESS, policy.access_token_ttl
    )

    refresh_token_exp, refresh_token = token_manager.create_token(
        session_id, user, access_tokens_integration.TokenType.REFRESH, policy.refresh_token_ttl
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
    token_manager: access_tokens_integration.TokenManager,
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
    return token_manager.create_token(
        session_id, user, access_tokens_integration.TokenType.ACCESS, policy.access_token_ttl
    )


def build_token_response(
    client_type: str,
    session_id: str,
    access_token: str,
    access_token_exp: datetime,
    refresh_token: str,
    refresh_token_exp: datetime,
    csrf_token: str,
) -> auth_schema.AuthOutcome:
    """Build the OAuth 2.1 token-response body for login and refresh.

    Single source of truth for token delivery, shared by the password
    login, SSO login, and ``/refresh`` flows so they cannot drift:

    - Web clients receive the refresh token as an ``HttpOnly`` cookie
      (set by the router from the returned outcome) and the CSRF token
      in the body.
    - Mobile clients receive the refresh token in the body and no CSRF
      token.

    ``expires_in`` / ``refresh_token_expires_in`` are seconds-until-expiry
    per RFC 6749 §5.1.

    Args:
        client_type: ``"web"`` or any other value (treated as mobile).
        session_id: Session identifier.
        access_token: Newly minted access token.
        access_token_exp: Access-token expiry datetime.
        refresh_token: Newly minted refresh token.
        refresh_token_exp: Refresh-token expiry datetime.
        csrf_token: CSRF token (only returned to web clients).

    Returns:
        The response body and, for a web client, the refresh cookie the router sets.
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
        # token in body for in-memory storage. The router sets the cookie
        # through deliver_auth_outcome so login, /refresh, and SSO token
        # exchange stay in lockstep.
        body["csrf_token"] = csrf_token
        return auth_schema.AuthOutcome(body, auth_schema.RefreshCookie(refresh_token, refresh_token_exp))

    # Mobile: All tokens in JSON body for secure platform storage.
    body["refresh_token"] = refresh_token
    return auth_schema.AuthOutcome(body)


def complete_login(
    ip_address: str,
    user_agent: str,
    user: users_schema.UsersRead,
    client_type: str,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
) -> auth_schema.AuthOutcome:
    """Handles the completion of the login process by generating session and authentication tokens,.

    storing the session in the database, and returning tokens in response body.

    OAuth 2.1 compliant: Returns tokens in response body for all clients.
    - Access token and CSRF token: Returned in body (for in-memory storage)
    - Refresh token: Set as httpOnly cookie with SameSite=Strict

    This unified model works for both username/password and SSO login flows.

    Args:
        ip_address (str): Client address, recorded on the session.
        user_agent (str): Client user agent, recorded on the session.
        user (users_schema.UsersRead): The authenticated user object.
        client_type (str): The type of client ("web" or "mobile").
        password_hasher (credentials_integration.PasswordHasher): Utility for password hashing.
        token_manager (access_tokens_integration.TokenManager): Utility for token generation and management.
        db (Session): Database session for storing session information.

    Returns:
        The token body (session_id, access_token, csrf_token, token_type, expires_in, refresh_token_expires_in) and,
        for web clients, the refresh cookie.

    Raises:
        PermissionDeniedError: If the client type is invalid.
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
    sessions_integration.create_session(
        session_id,
        user,
        ip_address,
        user_agent,
        refresh_token,
        password_hasher,
        refresh_token_exp,
        db,
    )
    db.commit()

    # Token delivery based on client type (web cookie vs mobile body) is
    # centralised in build_token_response so login, /refresh, and SSO
    # token exchange share one delivery contract.
    return build_token_response(
        client_type,
        session_id,
        access_token,
        access_token_exp,
        refresh_token,
        refresh_token_exp,
        csrf_token,
    )


def create_mobile_pkce_session_response(
    ip_address: str,
    user_agent: str,
    user: users_schema.UsersRead,
    code_challenge: str,
    code_challenge_method: str,
    password_hasher: credentials_integration.PasswordHasher,
    db: Session,
) -> auth_schema.MobileSessionRead:
    """Create a session for mobile password login with PKCE exchange flow.

    This function is exclusively for mobile clients. Web clients should use
    complete_login() which provides secure token delivery via httpOnly cookies.

    Similar to SSO flow, but for password authentication.
    Returns session_id instead of tokens—tokens obtained via
    POST /public/idp/session/{session_id}/tokens with code_verifier.

    Args:
        ip_address: Client address, recorded on the session
        user_agent: Client user agent, recorded on the session
        user: Authenticated user object
        code_challenge: PKCE code challenge (base64url-encoded SHA256)
        code_challenge_method: PKCE method (must be S256)
        password_hasher: Password hasher instance
        db: Database session

    Returns:
        auth_schema.MobileSessionRead: Contains session_id and mfa_required flag

    Raises:
        InvalidInputError: If PKCE parameters are invalid

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
    state_id, nonce = oauth_state_integration.create_state_id_and_nonce()

    oauth_state_integration.create_oauth_state(
        db=db,
        state_id=state_id,
        nonce=nonce,
        client_type="mobile",  # This function is mobile-only
        ip_address=ip_address,
        redirect_path=None,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    # Create session linked to oauth_state (enables PKCE exchange)
    sessions_integration.create_session(
        session_id,
        user,
        ip_address,
        user_agent,
        None,  # No refresh token yet
        password_hasher,
        datetime.now(UTC) + server_settings_integration.get_session_policy(db).refresh_token_ttl,
        db,
        oauth_state_id=state_id,
    )
    db.commit()
    logger.debug("Mobile PKCE session created", extra=core_logger.context(user_id=user.id))

    # Return session_id for token exchange (no tokens yet)
    return auth_schema.MobileSessionRead(
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
        InvalidInputError: If PKCE parameters are supplied partially.
    """
    if client_type != "mobile":
        return

    has_any_pkce_param = code_challenge is not None or code_challenge_method is not None
    has_complete_pkce_params = bool(code_challenge and code_challenge_method)

    if has_any_pkce_param and not has_complete_pkce_params:
        raise core_exceptions.InvalidInputError("code_challenge and code_challenge_method must be provided together")


def _raise_auth_security_store_unavailable(
    err: lockout_contracts.AuthSecurityStoreUnavailableError,
) -> None:
    """Return a controlled response when auth security storage is down.

    Args:
        err: Auth security storage outage.

    Returns:
        None.

    Raises:
        ServiceUnavailableError: Always raised.
    """
    logger.error("Auth security storage unavailable during authentication", exc_info=err)
    raise core_exceptions.ServiceUnavailableError("Authentication temporarily unavailable")


def _refuse_while_mfa_locked_out(username: str, pending_mfa_store: mfa_dependencies.PendingMFAStore) -> None:
    """Refuse an MFA attempt while the account is locked out from too many failed codes.

    Args:
        username: The account's username.
        pending_mfa_store: Store for pending MFA logins and the MFA lockout.

    Raises:
        TooManyRequestsError: If the account is locked out.
        ServiceUnavailableError: If the lockout store is down.
    """
    try:
        if pending_mfa_store.is_locked_out(username):
            lockout_until = pending_mfa_store.get_lockout_time(username)
            if lockout_until:
                seconds_remaining = int((lockout_until - datetime.now(UTC)).total_seconds())
                logger.warning(
                    "MFA attempt refused: account locked out",
                    extra=core_logger.context(
                        username_log_id=lockout_integration.username_log_identifier(username),
                        seconds_remaining=seconds_remaining,
                    ),
                )
                raise core_exceptions.TooManyRequestsError(
                    f"Too many failed MFA attempts. Account locked for {seconds_remaining} seconds."
                )
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)


def _require_valid_mfa_code(
    username: str,
    user_id: int,
    mfa_code: str,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    db: Session,
) -> None:
    """Check a TOTP or backup code, counting a failure toward the MFA lockout.

    A backup code the check consumes stays consumed: the commit happens before the caller finishes the login.

    Args:
        username: The account's username.
        user_id: The account's id.
        mfa_code: The submitted TOTP or backup code.
        pending_mfa_store: Store for pending MFA logins, the MFA lockout and the TOTP replay guard.
        db: Database session.

    Raises:
        InvalidMfaCodeError: If the code does not verify.
        ServiceUnavailableError: If the lockout store is down.
    """
    username_log_id = lockout_integration.username_log_identifier(username)
    if not mfa_integration.verify_user_mfa(
        user_id, mfa_code, credentials_integration, db, replay_guard=pending_mfa_store
    ):
        # Record failed attempt and apply lockout if threshold exceeded
        try:
            failed_count = pending_mfa_store.record_failed_attempt(username)
        except lockout_contracts.AuthSecurityStoreUnavailableError as err:
            _raise_auth_security_store_unavailable(err)
        lockout_integration.report_lockout_applied(
            "mfa", lockout_contracts.MFA_LOCKOUT_TIERS, failed_count, username=username
        )
        logger.warning(
            "Invalid MFA code for <username_log_id>. Failed attempts: <failed_count>",
            extra=core_logger.context(username_log_id=username_log_id, failed_count=failed_count),
        )
        raise core_exceptions.InvalidMfaCodeError(_INVALID_MFA_CODE_MESSAGE)
    db.commit()


def _finish_login(
    ip_address: str,
    user_agent: str,
    user: users_schema.UsersRead,
    client_type: str,
    code_challenge: str | None,
    code_challenge_method: str | None,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
) -> auth_schema.AuthOutcome:
    """Complete a verified login with tokens or, for a mobile PKCE client, a session to exchange.

    Args:
        ip_address: Client address, recorded on the session.
        user_agent: Client user agent, recorded on the session.
        user: The authenticated user.
        client_type: ``"web"`` or ``"mobile"``.
        code_challenge: PKCE code challenge, if the client sent one.
        code_challenge_method: PKCE challenge method, if the client sent one.
        password_hasher: Hasher for the stored refresh token.
        token_manager: Token manager that signs the tokens.
        db: Database session.

    Returns:
        The outcome of :func:`complete_login`, or the PKCE session body for a mobile PKCE client.
    """
    # Mobile clients with PKCE use secure token exchange flow
    # Web clients don't need PKCE - they have httpOnly cookies and same-origin protection
    if client_type == "mobile" and code_challenge and code_challenge_method:
        # Use PKCE exchange flow through the public IdP token exchange endpoint
        return auth_schema.AuthOutcome(
            create_mobile_pkce_session_response(
                ip_address, user_agent, user, code_challenge, code_challenge_method, password_hasher, db
            )
        )

    # Web clients and mobile without PKCE get tokens directly
    return complete_login(ip_address, user_agent, user, client_type, password_hasher, token_manager, db)


def login_for_access_token(
    ip_address: str,
    user_agent: str,
    username: str,
    password: str,
    client_type: str,
    failed_attempts: failed_login_store.FailedLoginStore,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
) -> auth_schema.AuthOutcome:
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
        ip_address: Client address, recorded on the session
        user_agent: Client user agent, recorded on the session
        username: Username presented by the client
        password: Password presented by the client
        client_type: The type of client making the request ("web" or "mobile")
        failed_attempts: Failed login attempts tracker for progressive lockout
        pending_mfa_store: Store for pending MFA logins
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        code_challenge: PKCE code challenge (base64url-encoded SHA256, optional for mobile)
        code_challenge_method: PKCE method (must be S256 if provided, optional for mobile)

    Returns:
        The outcome whose body is:
            - If MFA is required, an MFA-required response (schema or dict depending on client type)
            - If MFA is not required and mobile client with PKCE, the session_id for token exchange
            - If MFA is not required and no PKCE, the tokens from complete_login(), with the refresh cookie for web

    Raises:
        DomainError: If authentication fails (an inactive account included, with the same answer), or the
            account is locked
    """
    _validate_pkce_query_params(
        client_type,
        code_challenge,
        code_challenge_method,
    )

    # Check if username is locked out from too many failed login attempts
    try:
        if failed_attempts.is_locked_out(username):
            lockout_until = failed_attempts.get_lockout_time(username)
            if lockout_until:
                seconds_remaining = int((lockout_until - datetime.now(UTC)).total_seconds())
                logger.warning(
                    "Login refused: account locked out",
                    extra=core_logger.context(
                        username_log_id=lockout_integration.username_log_identifier(username),
                        seconds_remaining=seconds_remaining,
                    ),
                )
                raise core_exceptions.TooManyRequestsError(
                    f"Account locked due to too many failed login attempts. Try again in {seconds_remaining} seconds."
                )
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)

    # Authenticate user
    try:
        user = authenticate_user(username, password, password_hasher, db)
        if not user.active:
            # Answered and counted exactly like a wrong password, so the response never confirms that the
            # password of a deactivated or pending account is right.
            _refuse_credentials(username)
    except core_exceptions.UnauthenticatedError as err:
        # Record failed attempt on authentication errors (401 Unauthorized)
        if err.status_code == 401:
            try:
                login_failures = failed_attempts.record_failed_attempt(username)
            except lockout_contracts.AuthSecurityStoreUnavailableError as store_err:
                _raise_auth_security_store_unavailable(store_err)
            lockout_integration.report_lockout_applied(
                "login", lockout_contracts.LOGIN_LOCKOUT_TIERS, login_failures, username=username
            )
        raise err

    # Check if MFA is enabled for this user
    if mfa_integration.is_mfa_enabled_for_user(user.id, db):
        # Store the user for pending MFA verification
        try:
            mfa_challenge = pending_mfa_store.add_pending_login(user.id)
        except lockout_contracts.AuthSecurityStoreUnavailableError as err:
            _raise_auth_security_store_unavailable(err)

        # Don't reset failed login attempts yet - wait for MFA verification
        # This prevents bypassing lockout by triggering MFA flow

        # Return MFA required response
        if client_type == "web":
            return auth_schema.AuthOutcome(
                auth_schema.MFARequiredRead(
                    mfa_required=True,
                    username=username,
                    mfa_challenge=mfa_challenge,
                    message="MFA verification required",
                )
            )
        if client_type == "mobile":
            return auth_schema.AuthOutcome(
                {
                    "mfa_required": True,
                    "username": username,
                    "mfa_challenge": mfa_challenge,
                    "message": "MFA verification required",
                }
            )

    # Password authentication successful and no MFA required
    # Reset failed login attempts counter
    try:
        failed_attempts.reset_attempts(username)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)

    return _finish_login(
        ip_address,
        user_agent,
        user,
        client_type,
        code_challenge,
        code_challenge_method,
        password_hasher,
        token_manager,
        db,
    )


def verify_mfa_and_login(
    ip_address: str,
    user_agent: str,
    mfa_request: auth_schema.MFALoginRequest,
    client_type: str,
    failed_attempts: failed_login_store.FailedLoginStore,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
) -> auth_schema.AuthOutcome:
    """Verify MFA code and complete login process.

    This endpoint verifies the MFA code for a pending login and completes
    the authentication process if the code is valid.

    PKCE Support (Mobile):
    - Mobile clients can optionally provide code_challenge and code_challenge_method
    - For mobile clients with PKCE parameters, tokens are not returned directly
        - Instead, a session_id is returned for secure token exchange via
            /public/idp/session/{session_id}/tokens

    Args:
        ip_address: Client address, recorded on the session
        user_agent: Client user agent, recorded on the session
        failed_attempts: Failed login attempts tracker for progressive lockout
        mfa_request: MFA login request containing the login's challenge and the MFA code
        client_type: The type of client making the request ("web" or "mobile")
        pending_mfa_store: Store for pending MFA logins
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        code_challenge: PKCE code challenge (base64url-encoded SHA256, optional for mobile)
        code_challenge_method: PKCE method (must be S256 if provided, optional for mobile)

    Returns:
        The outcome of complete_login() or the PKCE session response

    Raises:
        DomainError: If the challenge or the MFA code is invalid (answered alike), or the user is not found
    """
    _validate_pkce_query_params(
        client_type,
        code_challenge,
        code_challenge_method,
    )

    # The challenge names the login; an unknown one answers exactly like a wrong code and counts against no
    # account, so neither guessing it nor knowing a username gets anyone further.
    try:
        user_id = pending_mfa_store.get_pending_login(mfa_request.mfa_challenge)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)
    if not user_id:
        # Run a dummy Argon2 verify so the wall-clock latency of the unknown-challenge branch matches the
        # wrong-code branch, where backup-code verification performs an Argon2 verify.
        password_hasher.dummy_verify()
        logger.warning("MFA verification refused: unknown or expired challenge")
        raise core_exceptions.InvalidMfaCodeError(_INVALID_MFA_CODE_MESSAGE)

    user = users_integration.get_user(user_id, db)
    if not user:
        logger.warning(
            "User ID <user_id> not found during MFA verification", extra=core_logger.context(user_id=user_id)
        )
        raise core_exceptions.UnauthenticatedError("Unable to authenticate", scheme="Bearer")

    _refuse_while_mfa_locked_out(user.username, pending_mfa_store)
    _require_valid_mfa_code(user.username, user_id, mfa_request.mfa_code, pending_mfa_store, db)

    try:
        claimed_user_id = pending_mfa_store.claim_pending_login(mfa_request.mfa_challenge)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)
    if claimed_user_id != user_id:
        logger.warning(
            "Pending MFA login for <username_log_id> was already claimed",
            extra=core_logger.context(username_log_id=lockout_integration.username_log_identifier(user.username)),
        )
        raise core_exceptions.InvalidMfaCodeError(_INVALID_MFA_CODE_MESSAGE)

    # Check if the user is still active
    users_integration.require_active_user(user)

    # MFA verification successful - reset both MFA and login failed attempts counters
    try:
        pending_mfa_store.reset_attempts(user.username)
        failed_attempts.reset_attempts(user.username)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        _raise_auth_security_store_unavailable(err)

    return _finish_login(
        ip_address,
        user_agent,
        user,
        client_type,
        code_challenge,
        code_challenge_method,
        password_hasher,
        token_manager,
        db,
    )


def _replay_rotation(
    client_type: str,
    session: sessions_contracts.SessionRead,
    refresh_token_value: str,
    token_user_id: int,
    token_manager: access_tokens_integration.TokenManager,
    policy: server_settings_contracts.SessionPolicy,
    db: Session,
) -> auth_schema.AuthOutcome:
    """Answer a refresh whose token was already rotated with the replacement minted by that rotation.

    The session is not rotated again (no new rotated record, no ``rotation_count`` bump), so duplicate
    and concurrent refreshes converge on one live refresh token.

    Args:
        client_type: Client type (``"web"`` or ``"mobile"``).
        session: The session the token belongs to.
        refresh_token_value: The raw refresh token that was already rotated.
        token_user_id: User ID extracted from the refresh token.
        token_manager: Utility for creating tokens.
        policy: The server's session policy.
        db: Database session.

    Returns:
        The outcome carrying the replacement refresh token.

    Raises:
        UnauthenticatedError: If the replacement is gone or the user cannot authenticate.
    """
    replay = rotated_refresh_tokens_integration.get_grace_replay_token(refresh_token_value, db)

    if replay is None:
        # Replacement was cleaned up (or never stored); fall back to the
        # standard invalid-token response.
        logger.warning(
            "Refresh token replay refused: no replacement stored for user <token_user_id>",
            extra=core_logger.context(token_user_id=token_user_id),
        )
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
        sessions_integration.update_session_csrf_token(session.id, replay_csrf_token, db)
        db.commit()

    return build_token_response(
        client_type,
        session.id,
        replay_access_token,
        replay_access_token_exp,
        replay_refresh_token,
        replay_refresh_token_exp,
        replay_csrf_token,
    )


def refresh_token(
    ip_address: str,
    user_agent: str,
    _validate_refresh_token: Callable,
    token_user_id: int,
    token_session_id: str,
    refresh_token_value: str,
    refresh_token_exp: datetime,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    client_type: str,
    db: Session,
    x_csrf_token: str | None = None,
) -> auth_schema.AuthOutcome:
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
        ip_address: Client address, recorded on the session.
        user_agent: Client user agent, recorded on the session.
        _validate_refresh_token: Dependency to validate the refresh token.
        token_user_id: User ID extracted from the refresh token.
        token_session_id: Session ID extracted from the refresh token.
        refresh_token_value: The raw refresh token value.
        refresh_token_exp: Expiry of the presented refresh token; its rotated record is kept until then.
        password_hasher: Utility for verifying token hashes.
        token_manager: Utility for creating tokens.
        db: Database session.
        client_type: Client type (\"web\" or \"mobile\").
        x_csrf_token: CSRF token header (web clients only, optional on page reload).


    Returns:
        The token body (session_id, access_token, csrf_token, token_type, expires_in, refresh_token_expires_in) and,
        for web clients, the refresh cookie.

    Raises:
        DomainError: If session not found, refresh token invalid,
                       user is inactive, or CSRF token is invalid (when provided).
    """
    # Get the session from the database
    session = sessions_integration.get_session_by_id_not_expired(token_session_id, db)

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
    sessions_integration.validate_session_timeout(session, policy)

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
        and not sessions_integration.verify_csrf_token(x_csrf_token, session.csrf_token_hash)
    ):
        # CSRF token was provided: validate it
        logger.warning(
            "Token refresh refused: invalid CSRF token for user <token_user_id>",
            extra=core_logger.context(token_user_id=token_user_id),
        )
        raise core_exceptions.PermissionDeniedError("Invalid CSRF token")

    # Verify session has a refresh token (not pending PKCE exchange)
    if not session.refresh_token:
        raise core_exceptions.UnauthenticatedError(
            "Tokens not yet exchanged via PKCE. Complete SSO/PKCE flow first.", scheme="Bearer"
        )

    # Check for token reuse BEFORE validating token
    # Uses HMAC-SHA256 internally for deterministic, secure lookup
    is_reused, in_grace = rotated_refresh_tokens_integration.check_token_reuse(refresh_token_value, db)

    if is_reused and not in_grace:
        # Token theft detected - invalidate entire family
        sessions_integration.invalidate_token_family(session.token_family_id, db)
        # The family stays invalidated although this request is refused.
        db.commit()
        logger.warning(
            "Refresh token reuse detected for user <token_user_id>; token family invalidated",
            extra=core_logger.context(token_user_id=token_user_id),
        )
        raise core_exceptions.UnauthenticatedError("Token reuse detected. All sessions invalidated.", scheme="Bearer")

    if is_reused and in_grace:
        # A retry inside the grace window (a lost rotation response, or a duplicate refresh) is answered
        # with the replacement minted on the original rotation; the session is not rotated again.
        return _replay_rotation(client_type, session, refresh_token_value, token_user_id, token_manager, policy, db)

    is_valid = password_hasher.verify_password(refresh_token_value, session.refresh_token)

    if not is_valid:
        logger.warning(
            "Token refresh refused: refresh token does not match session for user <token_user_id>",
            extra=core_logger.context(token_user_id=token_user_id),
        )
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
    try:
        rotated_refresh_tokens_integration.store_rotated_token(
            refresh_token_value,
            session.token_family_id,
            session.rotation_count,
            db,
            refresh_token_exp=refresh_token_exp,
            replacement_refresh_token=new_refresh_token,
            replacement_refresh_token_exp=new_refresh_token_exp,
        )
    except core_exceptions.ConflictError:
        # A concurrent request presenting the same token recorded its rotation first and wins; this one
        # answers with the winner's replacement instead of rotating the session a second time.
        db.rollback()
        return _replay_rotation(client_type, session, refresh_token_value, token_user_id, token_manager, policy, db)

    # Edit session and store in database
    # Note: edit_session automatically increments rotation_count
    # and updates last_rotation_at
    sessions_integration.edit_session(
        session,
        ip_address,
        user_agent,
        new_refresh_token,
        password_hasher,
        new_refresh_token_exp,
        db,
        new_csrf_token=new_csrf_token,
    )
    db.commit()

    # Retire expired IdP tokens now and queue the refresh of those about to expire; the provider
    # calls run on a worker, never in this request.
    identity_providers_integration.request_idp_token_refresh(user.id, db)
    db.commit()

    # Token delivery based on client type (web cookie vs mobile body) is
    # centralised in build_token_response so login, /refresh, and
    # SSO token exchange share one delivery contract.
    return build_token_response(
        client_type,
        session_id,
        new_access_token,
        new_access_token_exp,
        new_refresh_token,
        new_refresh_token_exp,
        new_csrf_token,
    )


def logout(
    _validate_refresh_token: Callable,
    token_session_id: str,
    refresh_token_value: str,
    client_type: str,
    token_user_id: int,
    password_hasher: credentials_integration.PasswordHasher,
    db: Session,
):
    """Log out a user by validating and deleting their session.

    Args:
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
        UnauthenticatedError: If the refresh token is invalid.
        PermissionDeniedError: If the client type is invalid.
    """
    # Get the session from the database
    session = sessions_integration.get_session_by_id_not_expired(token_session_id, db)

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
            logger.warning(
                "Logout refused: refresh token does not match session for user <token_user_id>",
                extra=core_logger.context(token_user_id=token_user_id),
            )
            raise core_exceptions.UnauthenticatedError("Invalid refresh token", scheme="Bearer")

        # Delete the session from the database
        sessions_integration.delete_session(session.id, token_user_id, db)
        db.commit()

        # Clear all IdP refresh tokens for security
        identity_providers_integration.clear_all_idp_tokens(token_user_id, db)
        db.commit()

    if client_type in ("web", "mobile"):
        return {"message": "Logout successful"}
    logger.warning("Logout refused for an unsupported client type")
    raise core_exceptions.PermissionDeniedError("Invalid client type")


def exchange_tokens_for_session(
    session_id: str,
    code_verifier: str,
    mfa_code: str | None,
    header_client_type: str | None,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
) -> auth_schema.AuthOutcome:
    """Exchange a PKCE code verifier for the tokens of an SSO session.

    The session was created by the identity-provider callback and holds no tokens yet. The caller proves it holds the
    verifier whose challenge the OAuth state stored; the exchange succeeds once per session.

    A session that came from an identity provider also needs an MFA code when the account has MFA enabled, since
    the provider's sign-in does not replace the account's own second factor. The code is checked after the PKCE
    verifier, so only the client that started the flow can try codes, and a wrong or missing code leaves the
    session unused for another attempt. A session from a password login has already passed MFA.

    Args:
        session_id: Session created by the identity-provider callback.
        code_verifier: PKCE verifier sent by the client.
        mfa_code: TOTP or backup code, if the client has one.
        header_client_type: ``X-Client-Type`` header of the exchange request, if any.
        pending_mfa_store: Store for the MFA lockout and the TOTP replay guard.
        password_hasher: Hasher for the stored refresh token.
        token_manager: Token manager that signs the tokens.
        db: Database session.

    Returns:
        The tokens; web clients get the refresh token as a cookie in the outcome, mobile clients in the body.

    Raises:
        NotFoundError: If the session does not exist or has no OAuth state.
        ConflictError: If the tokens were already exchanged, or another exchange won the race.
        InvalidInputError: If the OAuth state holds no PKCE data, the verifier does not match, or the client type
            contradicts the one recorded when the flow started.
        MfaRequiredError: If the account has MFA enabled and no code was sent.
        InvalidMfaCodeError: If the code does not verify.
        TooManyRequestsError: If the account is locked out from too many failed MFA codes.
    """
    fingerprint = core_hashing.log_fingerprint(session_id)
    session_with_state = sessions_integration.get_session_with_oauth_state(session_id, db)
    if not session_with_state:
        logger.warning(
            "Token exchange failed: session <value_1> not found", extra=core_logger.context(value_1=fingerprint)
        )
        raise core_exceptions.NotFoundError("Session not found or not eligible for token exchange")

    session_obj, oauth_state = session_with_state
    if not oauth_state:
        logger.warning(
            "Token exchange failed: session <value_1> has no OAuth state",
            extra=core_logger.context(value_1=fingerprint),
        )
        raise core_exceptions.NotFoundError("Session not eligible for PKCE token exchange")

    # Fast-path check; the atomic conditional update below is the authoritative guard against two concurrent
    # exchanges with the same verifier.
    if session_obj.tokens_exchanged:
        logger.warning(
            "Token exchange replay attempt for session <value_1>", extra=core_logger.context(value_1=fingerprint)
        )
        raise core_exceptions.ConflictError("Tokens already exchanged for this session")

    if not oauth_state.code_challenge or not oauth_state.code_challenge_method:
        logger.warning(
            "Token exchange failed: OAuth state <value_1> missing PKCE data",
            extra=core_logger.context(value_1=core_hashing.log_fingerprint(oauth_state.id)),
        )
        raise core_exceptions.InvalidInputError("OAuth state missing PKCE data")

    try:
        auth_computation.validate_pkce_verifier(
            code_verifier, oauth_state.code_challenge, oauth_state.code_challenge_method
        )
    except core_exceptions.InvalidInputError:
        logger.warning(
            "Token exchange failed: PKCE verification failed for session <value_1>",
            extra=core_logger.context(value_1=fingerprint),
        )
        raise

    # The client type recorded when the flow started wins over the header, so an exchange cannot switch between the
    # cookie-based web response and the body-only mobile response. The header is consulted only for a flow started by
    # a system browser, which cannot send it.
    stored_client_type = oauth_state.client_type
    if header_client_type not in ("web", "mobile"):
        header_client_type = None
    if stored_client_type in ("web", "mobile"):
        if header_client_type is not None and header_client_type != stored_client_type:
            logger.warning(
                "Token exchange client_type mismatch for session <value_1>: "
                "stored=<stored_client_type>, header=<header_client_type>",
                extra=core_logger.context(
                    value_1=fingerprint, stored_client_type=stored_client_type, header_client_type=header_client_type
                ),
            )
            raise core_exceptions.InvalidInputError("client_type does not match the OAuth state")
        client_type = stored_client_type
    else:
        client_type = header_client_type or "web"

    user = users_integration.require_user(session_obj.user_id, db)
    users_integration.require_active_user(user)

    if oauth_state.idp_id is not None and mfa_integration.is_mfa_enabled_for_user(user.id, db):
        if mfa_code is None:
            logger.info(
                "Token exchange for session <value_1> needs an MFA code", extra=core_logger.context(value_1=fingerprint)
            )
            raise core_exceptions.MfaRequiredError()
        _refuse_while_mfa_locked_out(user.username, pending_mfa_store)
        _require_valid_mfa_code(user.username, user.id, mfa_code, pending_mfa_store, db)
        try:
            pending_mfa_store.reset_attempts(user.username)
        except lockout_contracts.AuthSecurityStoreUnavailableError as err:
            _raise_auth_security_store_unavailable(err)

    (_, access_token_exp, access_token, refresh_token_exp, refresh_token, csrf_token) = create_tokens(
        user, token_manager, server_settings_integration.get_session_policy(db), session_id
    )
    now = datetime.now(UTC)
    expires_in = int((access_token_exp - now).total_seconds())
    refresh_token_expires_in = int((refresh_token_exp - now).total_seconds())

    # Store the refresh-token hash and mark the tokens exchanged in one conditional update. The CSRF hash is not
    # stored: the first /refresh after a page reload establishes the binding.
    if not sessions_integration.claim_session_for_token_exchange(
        session_id, password_hasher.hash_password(refresh_token), db
    ):
        logger.warning("Token exchange lost race for session <value_1>", extra=core_logger.context(value_1=fingerprint))
        raise core_exceptions.ConflictError("Tokens already exchanged for this session")
    db.commit()

    logger.info(
        "Token exchange successful for session <value_1> (user=<username_log_id>, client_type=<client_type>)",
        extra=core_logger.context(
            value_1=fingerprint,
            username_log_id=lockout_integration.username_log_identifier(user.username),
            client_type=client_type,
        ),
    )

    if client_type == "web":
        return auth_schema.AuthOutcome(
            auth_schema.TokenExchangeRead(
                session_id=session_id,
                access_token=access_token,
                csrf_token=csrf_token,
                expires_in=expires_in,
                refresh_token_expires_in=refresh_token_expires_in,
                token_type="Bearer",
            ),
            auth_schema.RefreshCookie(refresh_token, refresh_token_exp),
        )
    return auth_schema.AuthOutcome(
        auth_schema.TokenExchangeRead(
            session_id=session_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            refresh_token_expires_in=refresh_token_expires_in,
            token_type="Bearer",
        )
    )
