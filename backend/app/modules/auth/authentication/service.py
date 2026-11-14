"""Authentication workflows for login and token delivery."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import NoReturn

import jasil.audit as jasil_audit
from jasil.providers import StateProvider
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import core.network as core_network
import core.timezone as core_timezone
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.event_publishers as authentication_event_publishers
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.pending_password_change_store as pending_password_change_store
import modules.auth.authentication.refresh_service as authentication_refresh_service
import modules.auth.authentication.refusal_audit as authentication_refusal_audit
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.token_service as authentication_token_service
import modules.auth.computation as auth_computation
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.integration_service as identity_providers_integration
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
import modules.auth.rotated_refresh_tokens.integration_service as rotated_refresh_tokens_integration
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


#: The answer to a wrong MFA code; on the password MFA step, the challenge is still live.
_INVALID_MFA_CODE_MESSAGE = "Invalid MFA code, backup code or backup code already used."
#: The answer to a dead MFA challenge (unknown, expired, ended, mismatched or claimed); the client signs in again.
_DEAD_MFA_CHALLENGE_MESSAGE = "Unable to authenticate with provided credentials"


def _refuse_credentials(
    username: str,
    user_id: uuid.UUID | None = None,
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
        UnauthenticatedError: Always, with the ``Session`` challenge: the sign-in has no bearer scheme.
    """
    login_audit_integration.record_login_refusal(
        login_audit_actions.LoginMethod.PASSWORD, outcome, reason, user_id=user_id
    )
    logger.warning(
        "Sign-in refused for <username_log_id>",
        extra=core_logger.context(username_log_id=lockout_integration.username_log_identifier(username)),
    )
    raise core_exceptions.UnauthenticatedError("Unable to authenticate with provided credentials", scheme="Session")


def _record_failed_login(
    username: str,
    ip_address: str,
    user: users_schema.UserRead | None,
    failed_attempts: failed_login_store.FailedLoginStore,
    db: Session,
) -> None:
    """Count a refused password sign-in and, when it locks the account, audit that and tell the account's owner.

    Args:
        username: The username presented.
        ip_address: The client address of the sign-in.
        user: The account the username names, or None when it names none.
        failed_attempts: Failed login attempts tracker for progressive lockout.
        db: Database session.

    Raises:
        ServiceUnavailableError: If the shared lockout state is unavailable.
    """
    try:
        failure = failed_attempts.record_failed_attempt(username, ip_address, user_id=user.id if user else None)
    except lockout_contracts.AuthSecurityStoreUnavailableError as store_err:
        raise_auth_security_store_unavailable(store_err)
    lockout_integration.report_lockout_applied(
        "login", lockout_contracts.LOGIN_LOCKOUT_TIERS, failure.client_count, username=username
    )
    if not failure.account_locked_now:
        return
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
    user: users_schema.UserRead | None,
    username: str,
    password: str,
    password_hasher: credentials_integration.PasswordHasher,
    db: Session,
) -> users_schema.UserRead:
    """Authenticates a user by verifying the provided username and password.

    Args:
        user (users_schema.UserRead | None): The account the username names, already looked up, or None when there is
            none; the caller reads whatever it must stamp before the credential is verified.
        username (str): The username of the user attempting to authenticate.
        password (str): The plaintext password provided by the user.
        password_hasher (credentials_integration.PasswordHasher): An instance of the password hasher for verifying and updating password hashes.
        db (Session): The database session used for querying and updating user data.

    Returns:
        users_schema.UserRead: The authenticated user object if authentication is successful.

    Raises:
        UnauthenticatedError: If the username does not exist or the password is invalid.
    """
    # Check if the user exists and if the password is correct
    if not user:
        # Run the dummy Argon2 verifies a wrong password would cost (one, or two for a password that is not NFC) so
        # that the wall-clock latency of the "user not found" branch matches the "user found, wrong password" branch.
        # Without this, Argon2's deliberately-tuned ~hundreds-of-milliseconds verify time is trivially observable
        # from the network and lets an attacker enumerate valid usernames without ever tripping FailedLoginAttempts
        # (lockout is only recorded on 401, which the attacker does not care about while probing existence).
        credentials_integration.dummy_verify_password(password, password_hasher)
        _refuse_credentials(username)

    # Load the user's local credential from the auth-owned credential
    # table. A missing row means the account has no local password.
    credential = credentials_integration.get_credential(user.id, db)

    # User has no local password (SSO-only account). Treat identically
    # to "wrong password" so neither the response body nor the timing
    # discloses the account's auth modality. The dummy verifies keep
    # the latency consistent with a wrong password's Argon2 verifies.
    if credential is None:
        credentials_integration.dummy_verify_password(password, password_hasher)
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


def password_amr(*, mfa: bool) -> list[str]:
    """Return the ``amr`` of a password sign-in: the password, and the one-time code when a second factor was used."""
    if mfa:
        return [
            auth_constants.AuthMethod.LOCAL_CREDENTIAL,
            auth_constants.AuthMethod.ONE_TIME_CODE,
            auth_constants.AuthMethod.MULTI_FACTOR,
        ]
    return [auth_constants.AuthMethod.LOCAL_CREDENTIAL]


def complete_login(
    ip_address: str,
    user_agent: str,
    user: users_schema.UserRead,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    *,
    mfa: bool,
    security_generation: int | None,
    device_hash: str | None,
) -> auth_schema.AuthOutcome[auth_schema.TokenWebRead]:
    """Complete the password sign-in of a web client: create its session and tokens.

    The access token is returned in the body (for in-memory storage) and the refresh token as
    an ``HttpOnly`` cookie with ``SameSite=Strict``. A mobile client's session is created by
    :func:`create_mobile_pkce_session_response` and its tokens by the token exchange.

    The session is created only while the account's security generation is still ``security_generation``; the lock
    that check takes lasts until the session is committed, so a security change cannot end the account's sessions
    between the check and the insert.

    Args:
        ip_address (str): Client address, recorded on the session.
        user_agent (str): Client user agent, recorded on the session.
        user (users_schema.UserRead): The authenticated user object.
        token_manager (access_tokens_integration.TokenManager): Utility for token generation and management.
        db (Session): Database session for storing session information.
        mfa (bool): Whether a second factor was verified for this sign-in.
        security_generation (int | None): The generation read before the credential that justifies this sign-in was
            verified, or the one the sign-in's MFA or password-change challenge carries.
        device_hash (str | None): Digest of the known-device id the sign-in recorded, stored on the session so that
            forgetting the device ends it.

    Returns:
        The token body (session_id, access_token, token_type, expires_in, refresh_token_expires_in) and
        the refresh cookie.

    Raises:
        UnauthenticatedError: If the account's security changed after the sign-in's proof was created.
    """
    if not security_generation_integration.matches_locked(user.id, security_generation, db):
        _refuse_credentials(user.username, user.id, reason=login_audit_actions.LoginFailureReason.SECURITY_CHANGED)

    (
        session_id,
        access_token_exp,
        access_token,
        refresh_token_exp,
        refresh_token,
    ) = authentication_token_service.create_tokens(
        user, auth_constants.ClientType.WEB, token_manager, server_settings_integration.get_session_policy(db)
    )

    session = sessions_integration.create_session(
        session_id,
        user,
        auth_constants.ClientType.WEB,
        ip_address,
        user_agent,
        refresh_token,
        refresh_token_exp,
        db,
        amr=password_amr(mfa=mfa),
        device_hash=device_hash,
    )
    db.commit()
    logger.info("Login completed for user <user_id>", extra=core_logger.context(user_id=str(user.id)))

    return authentication_token_service.build_web_token_response(
        session_id,
        access_token,
        access_token_exp,
        refresh_token,
        refresh_token_exp,
        session.expires_at,
    )


def create_mobile_pkce_session_response(
    ip_address: str,
    user_agent: str,
    user: users_schema.UserRead,
    code_challenge: str | None,
    code_challenge_method: str | None,
    db: Session,
    *,
    security_generation: int | None,
    mfa: bool,
    device_hash: str | None,
) -> auth_schema.MobileSessionRead:
    """Create the session of a mobile sign-in, which the client exchanges for tokens with its PKCE verifier.

    The end of every verified mobile sign-in. Web clients use ``complete_login``, which delivers the refresh token
    in an ``HttpOnly`` cookie.

    Args:
        ip_address: Client address, recorded on the session
        user_agent: Client user agent, recorded on the session
        user: Authenticated user object
        code_challenge: PKCE code challenge (base64url-encoded SHA256)
        code_challenge_method: PKCE method (must be S256)
        db: Database session
        security_generation: The generation the exchange must still find; read before the credential that justifies
            this sign-in was verified, or the one the sign-in's MFA or password-change challenge carries.
        mfa: Whether a second factor was verified for this sign-in.
        device_hash: Digest of the known-device id the sign-in recorded, stored on the session so that forgetting the
            device ends it.

    Returns:
        auth_schema.MobileSessionRead: Contains the session_id to exchange for tokens

    Raises:
        InvalidInputError: If the PKCE parameters are missing or invalid
    """
    if code_challenge is None or code_challenge_method is None:
        raise core_exceptions.InvalidInputError("A mobile sign-in needs code_challenge and code_challenge_method")
    auth_computation.validate_pkce_challenge(code_challenge, code_challenge_method)

    session_id = uuid.uuid4()

    # The OAuth state record holds the PKCE challenge the exchange checks the verifier against.
    state_id, nonce = oauth_state_integration.create_state_id_and_nonce()

    oauth_state = oauth_state_integration.create_oauth_state(
        db=db,
        state_id=state_id,
        nonce=nonce,
        client_type="mobile",
        ip_address=ip_address,
        redirect_path=None,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
        security_generation=security_generation,
    )

    # The session has no refresh token until the exchange.
    sessions_integration.create_session(
        session_id,
        user,
        auth_constants.ClientType.MOBILE,
        ip_address,
        user_agent,
        None,
        core_timezone.to_utc_aware(oauth_state.expires_at),
        db,
        oauth_state_id=state_id,
        amr=password_amr(mfa=mfa),
        device_hash=device_hash,
    )
    db.commit()
    logger.debug("Mobile sign-in session created", extra=core_logger.context(user_id=str(user.id)))

    return auth_schema.MobileSessionRead(next_step="exchange", session_id=session_id)


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


def start_mfa_challenge(
    pending: mfa_dependencies.PendingLogin,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    db: Session,
) -> auth_schema.MFARequiredRead:
    """Store a sign-in whose first step succeeded and answer with the challenge its MFA step must send back.

    The caller's transaction is committed: it holds what the verified first step staged, such as a password rehash,
    and never a session, which the MFA step creates or claims.

    Args:
        pending: The sign-in, bound to the client type, client network and security generation of its first step.
        pending_mfa_store: Store for pending MFA logins.
        db: Database session.

    Returns:
        The MFA step, with the challenge and the kinds of code the account can answer with.

    Raises:
        ServiceUnavailableError: If the store is down.
    """
    try:
        mfa_challenge = pending_mfa_store.add_pending_login(pending)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)
    db.commit()
    logger.info("MFA step started for user <user_id>", extra=core_logger.context(user_id=str(pending.user_id)))
    return auth_schema.MFARequiredRead(
        next_step="mfa",
        mfa_challenge=mfa_challenge,
        methods=mfa_integration.get_sign_in_methods(pending.user_id, db),
    )


def complete_session_exchange(
    user: users_schema.UserRead,
    session_id: uuid.UUID,
    client_type: auth_constants.ClientType,
    session_amr: Sequence[str],
    ip_address: str,
    user_agent: str,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    *,
    idp_id: uuid.UUID | None,
    mfa: bool,
    device_id: str | None,
    state: StateProvider,
) -> auth_schema.AuthOutcome[auth_schema.TokenRead] | None:
    """Issue the tokens of a sign-in session that passed every check, claiming the session once.

    The session was created by a mobile password sign-in or an identity-provider callback and holds no tokens yet.
    The claim is one conditional update, so of two requests that reach it for one session only one issues tokens.
    An identity-provider sign-in is complete once its tokens are issued, so the transaction that commits the claim
    also stages what its callback left for the account (the link of an account matched by email, the profile sync
    and the link's last-login stamp), its known device and its ``auth.session.login`` row; a password sign-in
    recorded its device and row when its session was created. The callback's record is removed once that commits.

    Args:
        user: The account the session belongs to.
        session_id: The session to exchange.
        client_type: The session's client type, which the caller checked the request against.
        session_amr: The methods the session was created with.
        ip_address: Client address of the request.
        user_agent: Client user agent of the request.
        token_manager: Token manager that signs the tokens.
        db: Database session.
        idp_id: The provider the session signed in through, or None for a password sign-in.
        mfa: Whether a second factor was verified after the session was created.
        device_id: Device id from the browser's device cookie or the mobile app's ``X-Device-Id`` header, or None when
            the client sent no valid one.
        state: The platform state provider, which holds what an identity-provider callback staged.

    Returns:
        The tokens; a web client gets the refresh token as a cookie in the outcome, a mobile client in the body. An
        identity-provider sign-in also carries the device id the client keeps: in the outcome for the browser's
        cookie, in the body for the mobile app. None when another request claimed the session first, or what the
        callback staged can no longer be applied; nothing is committed then.

    Raises:
        StateUnavailableError: If the state store that holds what the callback staged is unavailable.
    """
    fingerprint = core_hashing.log_fingerprint(str(session_id))
    # The session records the second factor verified after it was created next to the methods it was created with.
    amr = list(session_amr)
    if mfa:
        amr = [*amr, auth_constants.AuthMethod.ONE_TIME_CODE, auth_constants.AuthMethod.MULTI_FACTOR]

    (_, access_token_exp, access_token, refresh_token_exp, refresh_token) = authentication_token_service.create_tokens(
        user, client_type, token_manager, server_settings_integration.get_session_policy(db), session_id
    )

    # Store the refresh-token hash, mark the tokens exchanged and extend the session from the end of the exchange
    # window to the refresh lifetime in one conditional update.
    session_expires_at = sessions_integration.claim_session_for_token_exchange(
        session_id, sessions_integration.hash_refresh_token(refresh_token), refresh_token_exp, amr, db
    )
    if session_expires_at is None:
        logger.warning("Token exchange lost race for session <value_1>", extra=core_logger.context(value_1=fingerprint))
        return None
    issued_device_id = None
    if idp_id is not None:
        # Applied only after the claim succeeded, so of two completions of one session only one writes anything.
        with login_audit_integration.acting_as_user(user.id):
            try:
                user = identity_providers_integration.apply_staged_sign_in(state, session_id, user, idp_id, db)
            except core_exceptions.SessionEndedError:
                db.rollback()
                logger.warning(
                    "Token exchange refused for session <value_1>: what its callback staged cannot be applied",
                    extra=core_logger.context(value_1=fingerprint),
                )
                return None
        sign_in = known_devices_integration.record_sign_in(
            user.id, device_id, ip_address, user_agent, known_devices_events.SignInMethod.IDENTITY_PROVIDER, db
        )
        issued_device_id = sign_in.device_id
        sessions_integration.set_session_device_hash(session_id, core_hashing.sha256_hex(issued_device_id), db)
        with login_audit_integration.acting_as_user(user.id):
            jasil_audit.stage(
                db,
                login_audit_actions.LOGIN,
                **login_audit_integration.user_target(user.id),
                details=login_audit_actions.LoginDetails(
                    method=login_audit_actions.LoginMethod.IDENTITY_PROVIDER, mfa=mfa, new_device=sign_in.new_device
                ),
            )
    db.commit()
    if idp_id is not None:
        identity_providers_integration.discard_staged_sign_in(state, session_id)

    logger.info(
        "Token exchange successful for session <value_1> (user=<username_log_id>, client_type=<client_type>)",
        extra=core_logger.context(
            value_1=fingerprint,
            username_log_id=lockout_integration.username_log_identifier(user.username),
            client_type=client_type,
        ),
    )

    if client_type == auth_constants.ClientType.WEB:
        web = authentication_token_service.build_web_token_response(
            session_id, access_token, access_token_exp, refresh_token, refresh_token_exp, session_expires_at
        )
        return auth_schema.AuthOutcome(web.body, web.refresh_cookie, device_id=issued_device_id)
    mobile = authentication_token_service.build_mobile_token_response(
        session_id,
        access_token,
        access_token_exp,
        refresh_token,
        refresh_token_exp,
        session_expires_at,
        device_id=issued_device_id,
    )
    return auth_schema.AuthOutcome(mobile.body)


def refuse_while_mfa_locked_out(
    username: str,
    ip_address: str,
    user_id: uuid.UUID,
    method: login_audit_actions.LoginMethod,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    device_id: str | None,
    db: Session,
) -> None:
    """Refuse an MFA attempt while the account is locked out from too many failed codes.

    A known device of the account is held by the tiered lock but not by the account-wide lock.

    Args:
        username: The account's username.
        ip_address: The client address of the request, whose network the tiered lock is kept for.
        user_id: The account's id.
        method: How the sign-in being completed started, for the audit trail.
        pending_mfa_store: Store for pending MFA logins and the MFA lockout.
        device_id: The device id the client sent, or None when it sent no valid one.
        db: Database session.

    Raises:
        TooManyRequestsError: If the account is locked out.
        ServiceUnavailableError: If the lockout store is down.
    """
    try:
        if pending_mfa_store.is_locked_out(username, ip_address, user_id=user_id):
            known_device = known_devices_integration.is_known_device(user_id, device_id, db)
            lockout_until = pending_mfa_store.get_lockout_time(
                username, ip_address, user_id=user_id, known_device=known_device
            )
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
                    scope=core_exceptions.TooManyRequestsScope.MFA,
                    retry_at=lockout_until,
                )
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)


def require_valid_mfa_code(
    username: str,
    ip_address: str,
    user_id: uuid.UUID,
    method: login_audit_actions.LoginMethod,
    mfa_code: str,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    password_hasher: credentials_integration.PasswordHasher,
    db: Session,
) -> None:
    """Check a TOTP or backup code, counting a failure toward the MFA lockout.

    A backup code the check accepts is consumed in the caller's transaction, not committed here: the caller commits
    it together with the sign-in it completes, so a sign-in that is refused afterwards leaves the code usable.

    Args:
        username: The account's username.
        ip_address: The client address of the request, whose network the wrong code is counted for.
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
            failure = pending_mfa_store.record_failed_attempt(username, ip_address, user_id=user_id)
        except lockout_contracts.AuthSecurityStoreUnavailableError as err:
            raise_auth_security_store_unavailable(err)
        lockout_integration.report_lockout_applied(
            "mfa", lockout_contracts.MFA_LOCKOUT_TIERS, failure.count, username=username, user_id=user_id
        )
        if failure.account_locked_now:
            lockout_integration.report_lockout_applied(
                "mfa_account",
                lockout_contracts.ACCOUNT_MFA_LOCKOUT_TIERS,
                lockout_contracts.ACCOUNT_MFA_LOCKOUT_TIERS[0][0],
                username=username,
                user_id=user_id,
            )
            # The request ends in a refusal, so the event is published on its own rather than staged for a commit.
            authentication_event_publishers.publish_mfa_locked(user_id, db)
        logger.warning(
            "Invalid MFA code for <username_log_id>. Failed attempts: <failed_count>",
            extra=core_logger.context(username_log_id=username_log_id, failed_count=failure.count),
        )
        login_audit_integration.record_login_refusal(
            method,
            jasil_audit.Outcome.FAILURE,
            login_audit_actions.LoginFailureReason.INVALID_MFA_CODE,
            mfa=True,
            user_id=user_id,
        )
        raise core_exceptions.InvalidMfaCodeError(_INVALID_MFA_CODE_MESSAGE)


def _refuse_mfa_challenge(
    reason: login_audit_actions.LoginFailureReason,
    method: login_audit_actions.LoginMethod,
    user_id: uuid.UUID | None = None,
) -> NoReturn:
    """Audit and log a dead MFA challenge, then answer with the one message every dead challenge shares.

    Args:
        reason: Why the challenge was refused.
        method: How the sign-in started; a password sign-in when the challenge names no sign-in.
        user_id: The account the challenge named, or None when it named none.

    Raises:
        SessionEndedError: Always, so the client signs in again.
    """
    logger.warning(
        "MFA verification refused: <reason>", extra=core_logger.context(reason=reason.value, user_id=str(user_id))
    )
    login_audit_integration.record_login_refusal(method, jasil_audit.Outcome.FAILURE, reason, mfa=True, user_id=user_id)
    raise core_exceptions.SessionEndedError(_DEAD_MFA_CHALLENGE_MESSAGE)


def _end_mfa_challenge(
    challenge: str,
    reason: login_audit_actions.LoginFailureReason,
    method: login_audit_actions.LoginMethod,
    user_id: uuid.UUID,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
) -> NoReturn:
    """End an MFA challenge that can never succeed, then refuse it like any dead challenge.

    Args:
        challenge: The challenge to end.
        reason: Why it can never succeed: a security change outdated it, or its identity-provider session ended.
        method: How the sign-in started.
        user_id: The account the challenge belongs to.
        pending_mfa_store: Store for pending MFA logins.

    Raises:
        SessionEndedError: Always, so the client signs in again.
        ServiceUnavailableError: If the store is down.
    """
    try:
        pending_mfa_store.claim_pending_login(challenge)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)
    _refuse_mfa_challenge(reason, method, user_id)


def _sign_in_method(pending: mfa_dependencies.PendingLogin) -> login_audit_actions.LoginMethod:
    """Return how the sign-in a pending MFA login belongs to started."""
    if pending.sso_session_id is not None:
        return login_audit_actions.LoginMethod.IDENTITY_PROVIDER
    return login_audit_actions.LoginMethod.PASSWORD


def _awaiting_sso_session(
    session_id: uuid.UUID, db: Session
) -> tuple[sessions_contracts.SessionRead, uuid.UUID | None] | None:
    """Return the identity-provider session an MFA challenge finishes and its provider, while it can be exchanged.

    An exchange that finished clears the session's OAuth state, so a session without one is used up.
    """
    found = sessions_integration.get_session_with_oauth_state(session_id, db)
    if found is None or found[1] is None:
        return None
    return found[0], found[1].idp_id


def _end_challenge_after_wrong_code(
    challenge: str, user_id: uuid.UUID, pending_mfa_store: mfa_dependencies.PendingMFAStore
) -> None:
    """Count a wrong code against its challenge and answer that the challenge is dead when it was the last allowed.

    Args:
        challenge: The challenge the wrong code was presented with.
        user_id: The account the challenge belongs to.
        pending_mfa_store: Store for pending MFA logins.

    Raises:
        SessionEndedError: If the wrong code ended the challenge.
        ServiceUnavailableError: If the store is down.
    """
    try:
        ended = pending_mfa_store.record_wrong_code(challenge)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)
    if ended:
        logger.warning(
            "MFA challenge ended after too many wrong codes", extra=core_logger.context(user_id=str(user_id))
        )
        raise core_exceptions.SessionEndedError(_DEAD_MFA_CHALLENGE_MESSAGE)


def finish_login(
    ip_address: str,
    user_agent: str,
    user: users_schema.UserRead,
    client_type: auth_constants.ClientType,
    code_challenge: str | None,
    code_challenge_method: str | None,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    *,
    mfa: bool,
    device_id: str | None,
    security_generation: int | None,
) -> auth_schema.AuthOutcome[auth_schema.FinishedLoginRead]:
    """Complete a verified login: a web client gets tokens, a mobile client a session to exchange.

    The sign-in is recorded against the user's known devices in the same transaction as its audit row and session.

    Args:
        ip_address: Client address, recorded on the session.
        user_agent: Client user agent, recorded on the session.
        user: The authenticated user.
        client_type: The client type.
        code_challenge: PKCE code challenge of the sign-in; a mobile client always has one.
        code_challenge_method: PKCE challenge method of the sign-in.
        token_manager: Token manager that signs the tokens.
        db: Database session.
        mfa: Whether a second factor was verified for this sign-in.
        device_id: Device id from the browser's device cookie or the mobile app's ``X-Device-Id`` header, or None
            when the client sent no valid one.
        security_generation: The generation the sign-in's session must still find, which a web client's
            :func:`complete_login` checks and a mobile client's exchange checks; see
            :func:`create_mobile_pkce_session_response`.

    Returns:
        The outcome of :func:`complete_login` with the device id a web browser keeps in its cookie, or for a mobile
        client the session body to exchange, which carries the device id it must keep.
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

    device_hash = core_hashing.sha256_hex(sign_in.device_id)
    # A mobile client never gets tokens from a sign-in: it exchanges the session with its PKCE verifier.
    if client_type == auth_constants.ClientType.MOBILE:
        session = create_mobile_pkce_session_response(
            ip_address,
            user_agent,
            user,
            code_challenge,
            code_challenge_method,
            db,
            security_generation=security_generation,
            mfa=mfa,
            device_hash=device_hash,
        )
        return auth_schema.AuthOutcome(session.model_copy(update={"device_id": sign_in.device_id}))

    # A web browser gets its refresh token as a cookie, and keeps its device id in a cookie that the router sets.
    outcome = complete_login(
        ip_address,
        user_agent,
        user,
        token_manager,
        db,
        mfa=mfa,
        security_generation=security_generation,
        device_hash=device_hash,
    )
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
    security_generation: int | None,
) -> auth_schema.PasswordChangeRequiredRead:
    """Answer a verified sign-in with the step that makes the owner choose a new password; no session is created.

    Args:
        user: The user whose password and second factor, if any, are verified.
        client_type: The client type of the sign-in.
        code_challenge: PKCE code challenge of a mobile sign-in; None for a web sign-in.
        code_challenge_method: PKCE challenge method of a mobile sign-in; None for a web sign-in.
        store: Store for pending password changes.
        db: Database session.
        mfa: Whether a second factor was verified for this sign-in.
        security_generation: The generation the challenge is stamped with; read before the credential was verified,
            or the one the sign-in's MFA challenge carries.

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
        security_generation=security_generation,
    )
    try:
        challenge = store.add(pending)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)

    # The password is verified, so persist a rehash staged by authenticate_user before answering the challenge.
    db.commit()
    logger.info(
        "Password change required for user <user_id> before sign-in", extra=core_logger.context(user_id=str(user.id))
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
    *,
    code_challenge: str | None,
    code_challenge_method: str | None,
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
    - Account lock: 100 failed password sign-ins in a row for one account, from any addresses, lock the account for
      30 days. The count restarts on a successful sign-in and expires after 30 days without a failure. A device the
      account has signed in from since its last security change (its device id is known) is not held by this lock,
      only by the client-network lockout and the password check. A successful sign-in, a completed password reset, a password change or an
      administrator setting the password lifts the lock. When it trips, the account's owner gets an email and an in-app notification.

    This endpoint authenticates a user using provided credentials, checks if the user is active,
    and determines if MFA is required. If MFA is enabled for the user, it stores the pending login
    and returns an MFA-required response. If an administrator set the password, it stores the pending
    password change and returns a password-change response, without a session. Otherwise, it completes
    the login process and returns the required information.

    PKCE (mobile):
    - A mobile client always sends code_challenge and code_challenge_method (checked by the login form), and a web
      client sends neither
    - A mobile sign-in never returns tokens: it returns a session_id to exchange for tokens at
      /auth/sessions/{session_id}/tokens with the PKCE verifier

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
        code_challenge: PKCE code challenge (base64url-encoded SHA256) of a mobile client; None for a web client
        code_challenge_method: PKCE method (S256) of a mobile client; None for a web client
        password_change_store: Store for pending password changes
        device_id: Device id from the browser's device cookie or the mobile app's X-Device-Id header, or None when
            the client sent no valid one

    Returns:
        The outcome whose body is:
            - If MFA is required, an MFA-required response
            - If an administrator set the password, a password-change response
            - Otherwise, for a mobile client the session_id to exchange for tokens, for a web client the tokens
              from complete_login() with the refresh cookie

    Raises:
        DomainError: If authentication fails (an inactive account included, with the same answer), or the
            account is locked
    """
    # Looked up before the lock check, which is keyed by the account's id, and for an unknown username too, so the
    # work does not tell a name that has an account from one that has none.
    known = users_integration.get_user_by_username(username, db)
    known_id = known.id if known else None

    # Check if the account is locked out from too many failed login attempts. A known device of the account is held
    # by the client-network lockout and the password check but not by the account-wide lock.
    try:
        if failed_attempts.is_locked_out(username, ip_address, user_id=known_id):
            known_device = known is not None and known_devices_integration.is_known_device(known.id, device_id, db)
            lockout_until = failed_attempts.get_lockout_time(
                username, ip_address, user_id=known_id, known_device=known_device
            )
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
                    scope=core_exceptions.TooManyRequestsScope.SIGN_IN,
                    retry_at=lockout_until,
                )
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)

    # Authenticate user
    try:
        # Read before the password is verified, so a security change that commits while the hash runs outdates the
        # proof this sign-in creates. An unknown username is refused by the verification, so its 0 is never stamped.
        security_generation = security_generation_integration.current_generation(known.id, db) if known else 0
        user = authenticate_user(known, username, password, password_hasher, db)
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
                extra=core_logger.context(user_id=str(user.id)),
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
            _record_failed_login(username, ip_address, known, failed_attempts, db)
        raise err

    # Check if MFA is enabled for this user
    if mfa_integration.is_mfa_enabled_for_user(user.id, db):
        # Store the login, with the client type, client network and PKCE challenge of the password step, for the MFA
        # step. The password is verified, so a rehash staged by authenticate_user is committed with it. The failed
        # login attempts are reset only when the MFA step succeeds, so starting MFA steps does not lift the lockout.
        return auth_schema.AuthOutcome(
            start_mfa_challenge(
                mfa_dependencies.PendingLogin(
                    user_id=user.id,
                    client_type=client_type,
                    code_challenge=code_challenge,
                    code_challenge_method=code_challenge_method,
                    client_network=core_network.client_network(ip_address),
                    security_generation=security_generation,
                ),
                pending_mfa_store,
                db,
            )
        )

    # Password authentication successful and no MFA required
    # Reset failed login attempts counter
    try:
        failed_attempts.reset_attempts(username, ip_address, user_id=user.id)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)

    if credentials_integration.is_password_change_required(user.id, db):
        return auth_schema.AuthOutcome(
            _require_password_change(
                user,
                client_type,
                code_challenge,
                code_challenge_method,
                password_change_store,
                db,
                mfa=False,
                security_generation=security_generation,
            )
        )

    finished = finish_login(
        ip_address,
        user_agent,
        user,
        client_type,
        code_challenge,
        code_challenge_method,
        token_manager,
        db,
        mfa=False,
        device_id=device_id,
        security_generation=security_generation,
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
    *,
    password_change_store: pending_password_change_store.PendingPasswordChangeStore,
    device_id: str | None,
    state: StateProvider,
) -> auth_schema.AuthOutcome[auth_schema.MFAVerifyRead]:
    """Verify MFA code and complete login process.

    This endpoint verifies the MFA code for a pending login and completes
    the authentication process if the code is valid. When an administrator set the
    password, it stores the pending password change and answers a password-change
    response instead, without a session.

    The step carries no PKCE values: the login record holds the client type, the client network and the PKCE
    challenge of the first step. A challenge that is unknown, expired, ended by three wrong codes, presented by
    the other client type or from another client network (an IPv4 address or an IPv6 /64), or claimed by a
    concurrent request is answered 401 and the client signs in again; a wrong code on a live challenge is answered
    400.

    The first step is a password sign-in or the exchange of an identity-provider session. A password sign-in gives a
    mobile client a session_id to exchange for tokens at /auth/sessions/{session_id}/tokens, never tokens. An
    identity-provider sign-in claims the session its exchange named, once, and gives either client that session's
    tokens; a session that expired, was deleted or was exchanged meanwhile ends the challenge with a 401 before any
    code is tried. What the identity-provider callback staged for the account (a link by email, the profile sync) is
    applied only after the code passed, in the transaction that claims the session; when it can no longer be applied
    the sign-in is refused with a 401 and nothing is written.

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
        password_change_store: Store for pending password changes
        device_id: Device id from the browser's device cookie or the mobile app's X-Device-Id header, or None when
            the client sent no valid one
        state: The platform state provider, which holds what an identity-provider callback staged for the account

    Returns:
        For a password sign-in, the outcome of complete_login() for a web client, the session response to exchange
        for a mobile client, or the password-change response; for an identity-provider sign-in, the session's tokens

    Raises:
        SessionEndedError: If the challenge is dead, as described above, the user is not found, or what the
            identity-provider callback staged can no longer be applied
        InvalidMfaCodeError: If the MFA code is wrong and the challenge is still live
        TooManyRequestsError: If the account is locked out from too many wrong codes
    """
    # The challenge names the login and counts against no account until it is found, so neither guessing it nor
    # knowing a username gets anyone further.
    try:
        pending = pending_mfa_store.get_pending_login(mfa_request.mfa_challenge)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)
    if pending is None:
        _refuse_mfa_challenge(
            login_audit_actions.LoginFailureReason.MFA_CHALLENGE_EXPIRED, login_audit_actions.LoginMethod.PASSWORD
        )
    method = _sign_in_method(pending)
    if pending.client_type != client_type:
        _refuse_mfa_challenge(login_audit_actions.LoginFailureReason.MFA_CHALLENGE_EXPIRED, method)
    if pending.client_network != core_network.client_network(ip_address):
        _refuse_mfa_challenge(
            login_audit_actions.LoginFailureReason.MFA_CHALLENGE_NETWORK_MISMATCH, method, pending.user_id
        )

    user_id = pending.user_id
    # Looked up before the generation is locked: a deleted user's generation row went with it, so locking would
    # have to create one for a user that no longer exists.
    user = users_integration.get_user(user_id, db)
    if not user:
        logger.warning(
            "User ID <user_id> not found during MFA verification", extra=core_logger.context(user_id=str(user_id))
        )
        raise core_exceptions.SessionEndedError("Unable to authenticate")
    # Checked before any code is tried, so a challenge that a security change outdated cannot be used to guess codes.
    # The lock it takes lasts until the sign-in below commits.
    if not security_generation_integration.matches_locked(user_id, pending.security_generation, db):
        _end_mfa_challenge(
            mfa_request.mfa_challenge,
            login_audit_actions.LoginFailureReason.SECURITY_CHANGED,
            method,
            user_id,
            pending_mfa_store,
        )
    # An identity-provider sign-in finishes the session its exchange named. One that can no longer be exchanged ends
    # the challenge before any code is tried; the claim below still decides a race for the same session.
    sso_session = None
    if pending.sso_session_id is not None:
        sso_session = _awaiting_sso_session(pending.sso_session_id, db)
        if sso_session is None:
            _end_mfa_challenge(
                mfa_request.mfa_challenge,
                login_audit_actions.LoginFailureReason.SSO_SESSION_ENDED,
                method,
                user_id,
                pending_mfa_store,
            )

    refuse_while_mfa_locked_out(user.username, ip_address, user_id, method, pending_mfa_store, device_id, db)
    try:
        require_valid_mfa_code(
            user.username,
            ip_address,
            user_id,
            method,
            mfa_request.mfa_code,
            pending_mfa_store,
            password_hasher,
            db,
        )
    except core_exceptions.InvalidMfaCodeError:
        _end_challenge_after_wrong_code(mfa_request.mfa_challenge, user_id, pending_mfa_store)
        raise

    try:
        claimed = pending_mfa_store.claim_pending_login(mfa_request.mfa_challenge)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)
    if claimed is None or claimed.user_id != user_id:
        _refuse_mfa_challenge(login_audit_actions.LoginFailureReason.MFA_CHALLENGE_CLAIMED, method, user_id)

    # Check if the user is still active
    users_integration.require_active_user(user)

    # MFA verification successful - reset the MFA failure counters and, for a password sign-in, the login ones
    try:
        pending_mfa_store.reset_attempts(user.username, ip_address, user_id=user.id)
        if sso_session is None:
            failed_attempts.reset_attempts(user.username, ip_address, user_id=user.id)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        raise_auth_security_store_unavailable(err)

    if sso_session is not None:
        session, idp_id = sso_session
        exchanged = complete_session_exchange(
            user,
            session.id,
            session.client_type,
            session.amr,
            ip_address,
            user_agent,
            token_manager,
            db,
            idp_id=idp_id,
            mfa=True,
            device_id=device_id,
            state=state,
        )
        if exchanged is None:
            # Another MFA step for the same session claimed it first, or what its callback staged can no longer be
            # applied; the backup code this one used stays unused.
            _refuse_mfa_challenge(login_audit_actions.LoginFailureReason.SSO_SESSION_ENDED, method, user_id)
        return auth_schema.AuthOutcome(exchanged.body, exchanged.refresh_cookie, exchanged.device_id)

    if credentials_integration.is_password_change_required(user.id, db):
        return auth_schema.AuthOutcome(
            _require_password_change(
                user,
                client_type,
                pending.code_challenge,
                pending.code_challenge_method,
                password_change_store,
                db,
                mfa=True,
                security_generation=pending.security_generation,
            )
        )

    finished = finish_login(
        ip_address,
        user_agent,
        user,
        client_type,
        pending.code_challenge,
        pending.code_challenge_method,
        token_manager,
        db,
        mfa=True,
        device_id=device_id,
        security_generation=pending.security_generation,
    )
    return auth_schema.AuthOutcome(finished.body, finished.refresh_cookie, finished.device_id)


def logout(
    token_session_id: uuid.UUID,
    refresh_token_value: str,
    token_user_id: uuid.UUID,
    client_type: auth_constants.ClientType,
    ip_address: str,
    user_agent: str,
    db: Session,
) -> str | None:
    """Log out a user by validating and deleting their session, and name where to end it at the identity provider.

    Logout is idempotent: a session that is gone, not yet exchanged, or whose stored refresh token is not the
    presented one is left as it is. A presented token that an earlier refresh already rotated is a reuse, as it is
    at refresh: outside the rotating client's grace window it ends the session's whole token family, because the
    token has leaked.

    The provider and ID token of an identity-provider sign-in are read before the session is deleted, because the
    sign-in is deleted with it. The deletion is committed first; only then is the provider's end-session endpoint
    resolved, which may reach the network for discovery, so no transaction spans it. The user-facing operation has
    already succeeded by then, so a provider failure there is logged and answers no URL: the Endurain session is
    ended and the provider session stays.

    Args:
        token_session_id: The session ID extracted from the refresh token.
        refresh_token_value: The refresh token value from the request.
        token_user_id: The user ID extracted from the refresh token.
        client_type: The type of client; a web client is sent back to the login page after the provider ends its
            session, a mobile client is not.
        ip_address: Client address of the request, compared with the one that rotated a token.
        user_agent: ``User-Agent`` of the request, compared likewise.
        db: Database session for CRUD operations.

    Returns:
        The identity provider's end-session URL, or None when the session did not sign in through a provider whose
        discovery document names an end-session endpoint, or no session was ended.
    """
    # Get the session from the database
    session = sessions_integration.get_session_by_id_not_expired(token_session_id, db)

    # Check if the session was found
    if session is None:
        return None

    # A session whose tokens are not yet exchanged (pending PKCE) is not this caller's to end
    if not session.refresh_token:
        return None

    # A stored token that is not the presented one means the presented token was rotated or revoked. A rotated token
    # used outside its grace window, or inside it by another client, was stolen: the family ends, as at refresh.
    if not sessions_integration.verify_refresh_token(refresh_token_value, session.refresh_token):
        is_reused, in_grace = rotated_refresh_tokens_integration.check_token_reuse(
            refresh_token_value, db, ip_address=ip_address, user_agent=user_agent
        )
        if is_reused and not in_grace:
            authentication_refresh_service.end_session_on_reuse(token_user_id, session.token_family_id, db)
        else:
            logger.warning(
                "Logout ended nothing: refresh token does not match session for user <token_user_id>",
                extra=core_logger.context(token_user_id=str(token_user_id)),
            )
        return None

    end_session = identity_providers_integration.read_end_session(session.id, db)

    # Delete the session from the database
    sessions_integration.delete_session(session.id, token_user_id, db)
    with authentication_refusal_audit.refresh_token_context(token_user_id):
        jasil_audit.stage(db, authentication_audit_actions.LOGOUT, **login_audit_integration.user_target(token_user_id))
    db.commit()

    if end_session is None:
        return None
    post_logout_redirect_uri = (
        f"{core_config.settings.ENDURAIN_HOST}/login" if client_type == auth_constants.ClientType.WEB else None
    )
    return identity_providers_integration.end_session_url(end_session, post_logout_redirect_uri)
