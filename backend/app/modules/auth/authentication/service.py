"""Authentication workflows for login and token delivery."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NoReturn
from uuid import uuid4

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.event_publishers as authentication_event_publishers
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.pending_password_change_store as pending_password_change_store
import modules.auth.authentication.refusal_audit as authentication_refusal_audit
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.token_service as authentication_token_service
import modules.auth.computation as auth_computation
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.known_devices.events as known_devices_events
import modules.auth.known_devices.integration_service as known_devices_integration
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.login_audit.integration_service as login_audit_integration
import modules.auth.mfa.dependencies as mfa_dependencies
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


#: The one answer to an MFA step that fails, whether the code or the challenge was wrong.
_INVALID_MFA_CODE_MESSAGE = "Invalid MFA code, backup code or backup code already used."


def _refuse_credentials(
    username: str,
    user_id: int | None = None,
    outcome: jasil_audit.Outcome = jasil_audit.Outcome.FAILURE,
    reason: login_audit_actions.LoginFailureReason = (login_audit_actions.LoginFailureReason.INVALID_CREDENTIALS),
) -> NoReturn:
    """Audit and log a refused sign-in, then answer with the one message every cause shares.

    The account is named by a hashed identifier, so the log shows repeated guesses at one account without
    holding the username.

    Args:
        username: The username presented.
        user_id: The account the username matched, or None when none did.
        outcome: ``FAILURE`` for a wrong credential, ``DENIED`` for a refusal by policy.
        reason: Why the sign-in was refused.

    Raises:
        UnauthenticatedError: Always.
    """
    login_audit_integration.record_login_refusal(
        login_audit_actions.LoginMethod.PASSWORD, outcome, reason, user_id=user_id
    )
    logger.warning(
        "Sign-in refused for <username_log_id>",
        extra=core_logger.context(username_log_id=lockout_integration.username_log_identifier(username)),
    )
    raise core_exceptions.UnauthenticatedError("Unable to authenticate with provided credentials", scheme="Bearer")


def _is_known_device_of(username: str, device_id: str | None, db: Session) -> bool:
    """Return whether the device id is one the account named by the username signs in from.

    A username that matches no account has no known device, so a locked unknown name and a locked account answer
    alike.

    Args:
        username: The username presented.
        device_id: The device id the client sent, or None when it sent no valid one.
        db: Database session.

    Returns:
        True when the id belongs to a known device of the matched account.
    """
    if device_id is None:
        return False
    user = users_integration.get_user_by_username(username, db)
    return user is not None and known_devices_integration.is_known_device(user.id, device_id, db)


def _record_failed_login(
    username: str, ip_address: str, failed_attempts: failed_login_store.FailedLoginStore, db: Session
) -> None:
    """Count a refused password sign-in and, when it locks the account, audit that and tell the account's owner.

    Args:
        username: The username presented.
        ip_address: The client address of the sign-in.
        failed_attempts: Failed login attempts tracker for progressive lockout.
        db: Database session.

    Raises:
        ServiceUnavailableError: If the shared lockout state is unavailable.
    """
    try:
        failure = failed_attempts.record_failed_attempt(username, ip_address)
    except lockout_contracts.AuthSecurityStoreUnavailableError as store_err:
        raise_auth_security_store_unavailable(store_err)
    lockout_integration.report_lockout_applied(
        "login", lockout_contracts.LOGIN_LOCKOUT_TIERS, failure.client_count, username=username
    )
    if not failure.account_locked_now:
        return
    user = users_integration.get_user_by_username(username, db)
    if user is None:
        return
    lockout_integration.report_lockout_applied(
        "login_account",
        lockout_contracts.ACCOUNT_LOGIN_LOCKOUT_TIERS,
        lockout_contracts.ACCOUNT_LOGIN_LOCKOUT_TIERS[0][0],
        username=username,
        user_id=user.id,
    )
    # The request ends in a refusal, so the event is published on its own rather than staged for a commit.
    authentication_event_publishers.publish_account_locked(user.id, db)


def authenticate_user(
    username: str,
    password: str,
    password_hasher: credentials_integration.PasswordHasher,
    db: Session,
) -> users_schema.UserRead:
    """Authenticates a user by verifying the provided username and password.

    Args:
        username (str): The username of the user attempting to authenticate.
        password (str): The plaintext password provided by the user.
        password_hasher (credentials_integration.PasswordHasher): An instance of the password hasher for verifying and updating password hashes.
        db (Session): The database session used for querying and updating user data.

    Returns:
        users_schema.UserRead: The authenticated user object if authentication is successful.

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

    # Load the user's local credential from the auth-owned credential
    # table. A missing row means the account has no local password.
    credential = credentials_integration.get_credential(user.id, db)

    # User has no local password (SSO-only account). Treat identically
    # to "wrong password" so neither the response body nor the timing
    # discloses the account's auth modality. The dummy verify keeps
    # the latency consistent with a normal Argon2 verify.
    if credential is None:
        password_hasher.dummy_verify()
        _refuse_credentials(username, user.id)

    # Verify password and get updated hash if applicable
    is_password_valid, updated_hash = credentials_integration.verify_and_update_password(
        password, credential.password_hash, password_hasher
    )
    if not is_password_valid:
        _refuse_credentials(username, user.id)

    # Update user hash if applicable. A rehash replaces the hash of the same password, so whether the owner must
    # change it stays as it was.
    if updated_hash:
        credentials_integration.set_local_password_hash(
            user.id, updated_hash, db, change_required=credential.password_change_required
        )

    # Return the user if the password is correct
    return user


def complete_login(
    ip_address: str,
    user_agent: str,
    user: users_schema.UserRead,
    client_type: auth_constants.ClientType,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
) -> auth_schema.AuthOutcome[auth_schema.TokenRead]:
    """Handles the completion of the login process by generating session and authentication tokens,.

    storing the session in the database, and returning tokens in response body.

    OAuth 2.1 compliant: Returns tokens in response body for all clients.
    - Access token and CSRF token: Returned in body (for in-memory storage)
    - Refresh token: Set as httpOnly cookie with SameSite=Strict

    This unified model works for both username/password and SSO login flows.

    Args:
        ip_address (str): Client address, recorded on the session.
        user_agent (str): Client user agent, recorded on the session.
        user (users_schema.UserRead): The authenticated user object.
        client_type (auth_constants.ClientType): The type of client.
        password_hasher (credentials_integration.PasswordHasher): Utility for password hashing.
        token_manager (access_tokens_integration.TokenManager): Utility for token generation and management.
        db (Session): Database session for storing session information.

    Returns:
        The token body (session_id, access_token, csrf_token, token_type, expires_in, refresh_token_expires_in) and,
        for web clients, the refresh cookie.
    """
    # Create the tokens
    (
        session_id,
        access_token_exp,
        access_token,
        refresh_token_exp,
        refresh_token,
        csrf_token,
    ) = authentication_token_service.create_tokens(
        user, token_manager, server_settings_integration.get_session_policy(db)
    )

    # Create the session and store it in the database
    # Note: csrf_token is NOT stored on initial login (csrf_token_hash = None).
    # This enables the OAuth 2.1 bootstrap pattern where the first /refresh call
    # after page reload establishes the CSRF binding. The httpOnly cookie is
    # sufficient authentication for the bootstrap refresh.
    session = sessions_integration.create_session(
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
    logger.info(
        "Login completed for user <user_id> (client_type=<client_type>)",
        extra=core_logger.context(user_id=user.id, client_type=client_type),
    )

    # Token delivery based on client type (web cookie vs mobile body) is
    # centralised in build_token_response so login, /refresh, and SSO
    # token exchange share one delivery contract.
    return authentication_token_service.build_token_response(
        client_type,
        session_id,
        access_token,
        access_token_exp,
        refresh_token,
        refresh_token_exp,
        session.expires_at,
        csrf_token,
    )


def create_mobile_pkce_session_response(
    ip_address: str,
    user_agent: str,
    user: users_schema.UserRead,
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
        auth_schema.MobileSessionRead: Contains the session_id to exchange for tokens

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

    oauth_state = oauth_state_integration.create_oauth_state(
        db=db,
        state_id=state_id,
        nonce=nonce,
        client_type="mobile",  # This function is mobile-only
        ip_address=ip_address,
        redirect_path=None,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
    )

    # Create session linked to oauth_state (enables PKCE exchange)
    sessions_integration.create_session(
        session_id,
        user,
        ip_address,
        user_agent,
        None,  # No refresh token yet
        password_hasher,
        core_timezone.to_utc_aware(oauth_state.expires_at),
        db,
        oauth_state_id=state_id,
    )
    db.commit()
    logger.debug("Mobile PKCE session created", extra=core_logger.context(user_id=user.id))

    # Return session_id for token exchange (no tokens yet)
    return auth_schema.MobileSessionRead(next_step="exchange", session_id=session_id)


def _validate_pkce_query_params(
    client_type: auth_constants.ClientType,
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
    if client_type != auth_constants.ClientType.MOBILE:
        return

    has_any_pkce_param = code_challenge is not None or code_challenge_method is not None
    has_complete_pkce_params = bool(code_challenge and code_challenge_method)

    if has_any_pkce_param and not has_complete_pkce_params:
        raise core_exceptions.InvalidInputError("code_challenge and code_challenge_method must be provided together")


def raise_auth_security_store_unavailable(
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


def refuse_while_mfa_locked_out(
    username: str,
    user_id: int,
    method: login_audit_actions.LoginMethod,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
) -> None:
    """Refuse an MFA attempt while the account is locked out from too many failed codes.

    Args:
        username: The account's username.
        user_id: The account's id.
        method: How the sign-in being completed started, for the audit trail.
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
                login_audit_integration.record_login_refusal(
                    method,
                    jasil_audit.Outcome.DENIED,
                    login_audit_actions.LoginFailureReason.LOCKED_OUT,
                    mfa=True,
                    user_id=user_id,
                )
                raise core_exceptions.TooManyRequestsError(
                    f"Too many failed MFA attempts. Account locked for {seconds_remaining} seconds.",
                    retry_at=lockout_until,
                )
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)


def require_valid_mfa_code(
    username: str,
    user_id: int,
    method: login_audit_actions.LoginMethod,
    mfa_code: str,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    password_hasher: credentials_integration.PasswordHasher,
    db: Session,
) -> None:
    """Check a TOTP or backup code, counting a failure toward the MFA lockout.

    A backup code the check consumes stays consumed: the commit happens before the caller finishes the login.

    Args:
        username: The account's username.
        user_id: The account's id.
        method: How the sign-in being completed started, for the audit trail.
        mfa_code: The submitted TOTP or backup code.
        pending_mfa_store: Store for pending MFA logins, the MFA lockout and the TOTP replay guard.
        password_hasher: Verifies a backup code against its stored hash.
        db: Database session.

    Raises:
        InvalidMfaCodeError: If the code does not verify.
        ServiceUnavailableError: If the lockout store is down.
    """
    username_log_id = lockout_integration.username_log_identifier(username)
    # A backup code is audited as used by the user who presented it, who has no principal yet.
    with jasil_audit.audit_context(
        actor_type=jasil_audit.ActorType.USER, actor_id=str(user_id), credential_type="password"
    ):
        code_is_valid = mfa_integration.verify_user_mfa(
            user_id, mfa_code, password_hasher, db, replay_guard=pending_mfa_store
        )
    if not code_is_valid:
        # Record failed attempt and apply lockout if threshold exceeded
        try:
            failed_count = pending_mfa_store.record_failed_attempt(username)
        except lockout_contracts.AuthSecurityStoreUnavailableError as err:
            raise_auth_security_store_unavailable(err)
        lockout_integration.report_lockout_applied(
            "mfa", lockout_contracts.MFA_LOCKOUT_TIERS, failed_count, username=username, user_id=user_id
        )
        logger.warning(
            "Invalid MFA code for <username_log_id>. Failed attempts: <failed_count>",
            extra=core_logger.context(username_log_id=username_log_id, failed_count=failed_count),
        )
        login_audit_integration.record_login_refusal(
            method,
            jasil_audit.Outcome.FAILURE,
            login_audit_actions.LoginFailureReason.INVALID_MFA_CODE,
            mfa=True,
            user_id=user_id,
        )
        raise core_exceptions.InvalidMfaCodeError(_INVALID_MFA_CODE_MESSAGE)
    db.commit()


def finish_login(
    ip_address: str,
    user_agent: str,
    user: users_schema.UserRead,
    client_type: auth_constants.ClientType,
    code_challenge: str | None,
    code_challenge_method: str | None,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    *,
    mfa: bool,
    device_id: str | None,
) -> auth_schema.AuthOutcome[auth_schema.FinishedLoginRead]:
    """Complete a verified login with tokens or, for a mobile PKCE client, a session to exchange.

    The sign-in is recorded against the user's known devices in the same transaction as its audit row and session.

    Args:
        ip_address: Client address, recorded on the session.
        user_agent: Client user agent, recorded on the session.
        user: The authenticated user.
        client_type: The client type.
        code_challenge: PKCE code challenge, if the client sent one.
        code_challenge_method: PKCE challenge method, if the client sent one.
        password_hasher: Hasher for the stored refresh token.
        token_manager: Token manager that signs the tokens.
        db: Database session.
        mfa: Whether a second factor was verified for this sign-in.
        device_id: Device id from the browser's device cookie or the mobile app's ``X-Device-Id`` header, or None
            when the client sent no valid one.

    Returns:
        The outcome of :func:`complete_login` with the device id a web browser keeps in its cookie, or the PKCE
        session body for a mobile PKCE client. A mobile client's body carries the device id it must keep.
    """
    sign_in = known_devices_integration.record_sign_in(
        user.id, device_id, ip_address, user_agent, known_devices_events.SignInMethod.PASSWORD, db
    )
    # The sign-in is audited in the transaction that the session creation below commits. The user has no
    # principal yet, so the context names them.
    with jasil_audit.audit_context(
        actor_type=jasil_audit.ActorType.USER, actor_id=str(user.id), credential_type="password"
    ):
        jasil_audit.stage(
            db,
            login_audit_actions.LOGIN,
            **login_audit_integration.user_target(user.id),
            details=login_audit_actions.LoginDetails(
                method=login_audit_actions.LoginMethod.PASSWORD, mfa=mfa, new_device=sign_in.new_device
            ),
        )

    # Mobile clients with PKCE use secure token exchange flow
    # Web clients don't need PKCE - they have httpOnly cookies and same-origin protection
    if client_type == auth_constants.ClientType.MOBILE and code_challenge and code_challenge_method:
        # Use PKCE exchange flow through the public IdP token exchange endpoint
        session = create_mobile_pkce_session_response(
            ip_address, user_agent, user, code_challenge, code_challenge_method, password_hasher, db
        )
        return auth_schema.AuthOutcome(session.model_copy(update={"device_id": sign_in.device_id}))

    # Web clients and mobile without PKCE get tokens directly
    outcome = complete_login(ip_address, user_agent, user, client_type, password_hasher, token_manager, db)
    if isinstance(outcome.body, auth_schema.TokenMobileRead):
        return auth_schema.AuthOutcome(outcome.body.model_copy(update={"device_id": sign_in.device_id}))
    # A web browser keeps its device id in a cookie that the router sets from the outcome.
    return auth_schema.AuthOutcome(outcome.body, outcome.refresh_cookie, device_id=sign_in.device_id)


def _require_password_change(
    user: users_schema.UserRead,
    client_type: auth_constants.ClientType,
    code_challenge: str | None,
    code_challenge_method: str | None,
    store: pending_password_change_store.PendingPasswordChangeStore,
    db: Session,
    *,
    mfa: bool,
) -> auth_schema.PasswordChangeRequiredRead:
    """Answer a verified sign-in with the step that makes the owner choose a new password; no session is created.

    Args:
        user: The user whose password and second factor, if any, are verified.
        client_type: The client type of the sign-in.
        code_challenge: PKCE code challenge, if the client sent one.
        code_challenge_method: PKCE challenge method, if the client sent one.
        store: Store for pending password changes.
        db: Database session.
        mfa: Whether a second factor was verified for this sign-in.

    Returns:
        The body that carries the challenge the password-change step must send back.

    Raises:
        ServiceUnavailableError: If the shared state is unavailable.
    """
    pending = pending_password_change_store.PendingPasswordChange(
        user_id=user.id,
        client_type=client_type,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        mfa=mfa,
    )
    try:
        challenge = store.add(pending)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)

    # The password is verified, so persist a rehash staged by authenticate_user before answering the challenge.
    db.commit()
    logger.info(
        "Password change required for user <user_id> before sign-in", extra=core_logger.context(user_id=user.id)
    )
    return auth_schema.PasswordChangeRequiredRead(next_step="password_change", password_change_challenge=challenge)


def login_for_access_token(
    ip_address: str,
    user_agent: str,
    username: str,
    password: str,
    client_type: auth_constants.ClientType,
    failed_attempts: failed_login_store.FailedLoginStore,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    *,
    password_change_store: pending_password_change_store.PendingPasswordChangeStore,
    device_id: str | None,
) -> auth_schema.AuthOutcome[auth_schema.LoginRead]:
    """Handles user login and access token generation, including Multi-Factor Authentication (MFA) flow.

    Protection Mechanisms:
    - Rate limiting: 10 requests per minute per IP (SENSITIVE tier, prevents DoS attacks)
    - Progressive lockout: Per-username and client-network tracking (an IPv6 address counts by its /64) prevents
      targeted brute-force without letting one client lock the account for everyone:
      * 5 failures: 5 minute lockout
      * 10 failures: 30 minute lockout
      * 20 failures: 24 hour lockout
    - Account lock: 100 failed password sign-ins in a row for one username, from any addresses, lock the account for
      30 days. The count restarts on a successful sign-in and expires after 30 days without a failure. A device the
      account has signed in from before (its device id is known) is not held by this lock, only by the client-network
      lockout and the password check. A successful sign-in, a completed password reset, a password change or an
      administrator setting the password lifts the lock. When it trips, the account's owner gets an email and an in-app notification.

    This endpoint authenticates a user using provided credentials, checks if the user is active,
    and determines if MFA is required. If MFA is enabled for the user, it stores the pending login
    and returns an MFA-required response. If an administrator set the password, it stores the pending
    password change and returns a password-change response, without a session. Otherwise, it completes
    the login process and returns the required information.

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
        client_type: The type of client making the request
        failed_attempts: Failed login attempts tracker for progressive lockout
        pending_mfa_store: Store for pending MFA logins
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        code_challenge: PKCE code challenge (base64url-encoded SHA256, optional for mobile)
        code_challenge_method: PKCE method (must be S256 if provided, optional for mobile)
        password_change_store: Store for pending password changes
        device_id: Device id from the browser's device cookie or the mobile app's X-Device-Id header, or None when
            the client sent no valid one

    Returns:
        The outcome whose body is:
            - If MFA is required, an MFA-required response (schema or dict depending on client type)
            - If an administrator set the password, a password-change response
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

    # Check if username is locked out from too many failed login attempts. A known device of the account is held
    # by the client-network lockout and the password check but not by the account-wide lock.
    try:
        if failed_attempts.is_locked_out(username, ip_address):
            known_device = _is_known_device_of(username, device_id, db)
            lockout_until = failed_attempts.get_lockout_time(username, ip_address, known_device=known_device)
            if lockout_until:
                seconds_remaining = int((lockout_until - datetime.now(UTC)).total_seconds())
                logger.warning(
                    "Login refused: account locked out",
                    extra=core_logger.context(
                        username_log_id=lockout_integration.username_log_identifier(username),
                        seconds_remaining=seconds_remaining,
                    ),
                )
                login_audit_integration.record_login_refusal(
                    login_audit_actions.LoginMethod.PASSWORD,
                    jasil_audit.Outcome.DENIED,
                    login_audit_actions.LoginFailureReason.LOCKED_OUT,
                )
                raise core_exceptions.TooManyRequestsError(
                    f"Account locked due to too many failed login attempts. Try again in {seconds_remaining} seconds.",
                    retry_at=lockout_until,
                )
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)

    # Authenticate user
    try:
        user = authenticate_user(username, password, password_hasher, db)
        if not user.active:
            # Answered and counted exactly like a wrong password, so the response never confirms that the
            # password of a deactivated or pending account is right.
            _refuse_credentials(
                username,
                user.id,
                jasil_audit.Outcome.DENIED,
                login_audit_actions.LoginFailureReason.INACTIVE,
            )
        if not credentials_integration.allows_password_sign_in(
            server_settings_integration.get_server_settings(db), users_schema.normalize_access_type(user.access_type)
        ):
            # Local sign-in is turned off and the account is not an administrator's. Answered like a wrong
            # password for the same reason.
            logger.warning(
                "Password sign-in refused for user <user_id>: local sign-in is disabled",
                extra=core_logger.context(user_id=user.id),
            )
            _refuse_credentials(
                username,
                user.id,
                jasil_audit.Outcome.DENIED,
                login_audit_actions.LoginFailureReason.PASSWORD_SIGN_IN_DISABLED,
            )
    except core_exceptions.UnauthenticatedError as err:
        # Record failed attempt on authentication errors (401 Unauthorized)
        if err.status_code == 401:
            _record_failed_login(username, ip_address, failed_attempts, db)
        raise err

    # Check if MFA is enabled for this user
    if mfa_integration.is_mfa_enabled_for_user(user.id, db):
        # Store the user for pending MFA verification
        try:
            mfa_challenge = pending_mfa_store.add_pending_login(user.id)
        except lockout_contracts.AuthSecurityStoreUnavailableError as err:
            raise_auth_security_store_unavailable(err)

        # The password is verified, so persist a rehash staged by authenticate_user before answering the challenge.
        db.commit()

        # Don't reset failed login attempts yet - wait for MFA verification
        # This prevents bypassing lockout by triggering MFA flow

        # Return MFA required response
        return auth_schema.AuthOutcome(auth_schema.MFARequiredRead(next_step="mfa", mfa_challenge=mfa_challenge))

    # Password authentication successful and no MFA required
    # Reset failed login attempts counter
    try:
        failed_attempts.reset_attempts(username, ip_address)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)

    if credentials_integration.is_password_change_required(user.id, db):
        return auth_schema.AuthOutcome(
            _require_password_change(
                user, client_type, code_challenge, code_challenge_method, password_change_store, db, mfa=False
            )
        )

    finished = finish_login(
        ip_address,
        user_agent,
        user,
        client_type,
        code_challenge,
        code_challenge_method,
        password_hasher,
        token_manager,
        db,
        mfa=False,
        device_id=device_id,
    )
    return auth_schema.AuthOutcome(finished.body, finished.refresh_cookie, finished.device_id)


def verify_mfa_and_login(
    ip_address: str,
    user_agent: str,
    mfa_request: auth_schema.MFALoginRequest,
    client_type: auth_constants.ClientType,
    failed_attempts: failed_login_store.FailedLoginStore,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    *,
    password_change_store: pending_password_change_store.PendingPasswordChangeStore,
    device_id: str | None,
) -> auth_schema.AuthOutcome[auth_schema.MFAVerifyRead]:
    """Verify MFA code and complete login process.

    This endpoint verifies the MFA code for a pending login and completes
    the authentication process if the code is valid. When an administrator set the
    password, it stores the pending password change and answers a password-change
    response instead, without a session.

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
        client_type: The type of client making the request
        pending_mfa_store: Store for pending MFA logins
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        code_challenge: PKCE code challenge (base64url-encoded SHA256, optional for mobile)
        code_challenge_method: PKCE method (must be S256 if provided, optional for mobile)
        password_change_store: Store for pending password changes
        device_id: Device id from the browser's device cookie or the mobile app's X-Device-Id header, or None when
            the client sent no valid one

    Returns:
        The outcome of complete_login(), the PKCE session response, or the password-change response

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
        raise_auth_security_store_unavailable(err)
    if not user_id:
        # Run a dummy Argon2 verify so the wall-clock latency of the unknown-challenge branch matches the
        # wrong-code branch, where backup-code verification performs an Argon2 verify.
        password_hasher.dummy_verify()
        logger.warning("MFA verification refused: unknown or expired challenge")
        login_audit_integration.record_login_refusal(
            login_audit_actions.LoginMethod.PASSWORD,
            jasil_audit.Outcome.FAILURE,
            login_audit_actions.LoginFailureReason.MFA_CHALLENGE_EXPIRED,
            mfa=True,
        )
        raise core_exceptions.InvalidMfaCodeError(_INVALID_MFA_CODE_MESSAGE)

    user = users_integration.get_user(user_id, db)
    if not user:
        logger.warning(
            "User ID <user_id> not found during MFA verification", extra=core_logger.context(user_id=user_id)
        )
        raise core_exceptions.UnauthenticatedError("Unable to authenticate", scheme="Bearer")

    password_method = login_audit_actions.LoginMethod.PASSWORD
    refuse_while_mfa_locked_out(user.username, user_id, password_method, pending_mfa_store)
    require_valid_mfa_code(
        user.username, user_id, password_method, mfa_request.mfa_code, pending_mfa_store, password_hasher, db
    )

    try:
        claimed_user_id = pending_mfa_store.claim_pending_login(mfa_request.mfa_challenge)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)
    if claimed_user_id != user_id:
        logger.warning(
            "Pending MFA login for <username_log_id> was already claimed",
            extra=core_logger.context(username_log_id=lockout_integration.username_log_identifier(user.username)),
        )
        login_audit_integration.record_login_refusal(
            password_method,
            jasil_audit.Outcome.FAILURE,
            login_audit_actions.LoginFailureReason.MFA_CHALLENGE_CLAIMED,
            mfa=True,
            user_id=user_id,
        )
        raise core_exceptions.InvalidMfaCodeError(_INVALID_MFA_CODE_MESSAGE)

    # Check if the user is still active
    users_integration.require_active_user(user)

    # MFA verification successful - reset both MFA and login failed attempts counters
    try:
        pending_mfa_store.reset_attempts(user.username)
        failed_attempts.reset_attempts(user.username, ip_address)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)

    if credentials_integration.is_password_change_required(user.id, db):
        return auth_schema.AuthOutcome(
            _require_password_change(
                user, client_type, code_challenge, code_challenge_method, password_change_store, db, mfa=True
            )
        )

    finished = finish_login(
        ip_address,
        user_agent,
        user,
        client_type,
        code_challenge,
        code_challenge_method,
        password_hasher,
        token_manager,
        db,
        mfa=True,
        device_id=device_id,
    )
    return auth_schema.AuthOutcome(finished.body, finished.refresh_cookie, finished.device_id)


def logout(
    token_session_id: str,
    refresh_token_value: str,
    token_user_id: int,
    password_hasher: credentials_integration.PasswordHasher,
    db: Session,
) -> None:
    """Log out a user by validating and deleting their session.

    Args:
        token_session_id: The session ID extracted from the refresh token.
        refresh_token_value: The refresh token value from the request.
        token_user_id: The user ID extracted from the refresh token.
        password_hasher: Utility for verifying the refresh token.
        db: Database session for CRUD operations.

    Raises:
        UnauthenticatedError: If the refresh token is invalid.
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
        with authentication_refusal_audit.refresh_token_context(token_user_id):
            jasil_audit.stage(
                db, authentication_audit_actions.LOGOUT, **login_audit_integration.user_target(token_user_id)
            )
        db.commit()
