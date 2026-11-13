"""Exchange of a sign-in session and its PKCE verifier for tokens."""

from __future__ import annotations

import uuid

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as authentication_service
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
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)

#: The answer to a session that is gone, outdated by a security change, or already exchanged.
_SESSION_NOT_ELIGIBLE_MESSAGE = "Session not found or not eligible for token exchange"

#: The one answer to a verifier that does not match, whether the code or the client type was wrong.
_INVALID_VERIFIER_MESSAGE = "Invalid code_verifier"


def _record_refusal(
    outcome: jasil_audit.Outcome, reason: login_audit_actions.LoginFailureReason, user_id: uuid.UUID
) -> None:
    """Audit a refused SSO token exchange, which signs in the account its session was created for.

    Args:
        outcome: ``FAILURE`` for a bad verifier or an outdated session, ``DENIED`` for a refusal by policy.
        reason: Why the exchange was refused.
        user_id: The account the session belongs to.
    """
    login_audit_integration.record_login_refusal(
        login_audit_actions.LoginMethod.IDENTITY_PROVIDER, outcome, reason, user_id=user_id
    )


def exchange_tokens_for_session(
    session_id: str,
    code_verifier: str,
    mfa_code: str | None,
    client_type: auth_constants.ClientType,
    ip_address: str,
    user_agent: str,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    *,
    device_id: str | None,
) -> auth_schema.AuthOutcome[auth_schema.TokenRead]:
    """Exchange a PKCE code verifier for the tokens of a session a sign-in created.

    The session was created by a mobile password sign-in or the identity-provider callback and holds no tokens yet.
    The caller proves it holds the verifier whose challenge the OAuth state stored; the exchange succeeds once per
    session; a second one finds the session without its OAuth state and is answered like an unknown session. The
    client type recorded when the sign-in started is the only one that can redeem it, and a different ``X-Client-Type`` is refused like a wrong verifier.

    A session that came from an identity provider also needs an MFA code when the account has MFA enabled, since
    the provider's sign-in does not replace the account's own second factor. The code is checked after the PKCE
    verifier, so only the client that started the flow can try codes, and a wrong or missing code leaves the
    session unused for another attempt. A session from a password login has already passed MFA.

    Args:
        session_id: Session created by the sign-in.
        code_verifier: PKCE verifier sent by the client.
        mfa_code: TOTP or backup code, if the client has one.
        client_type: ``X-Client-Type`` header of the exchange request.
        ip_address: Client address of the exchange request.
        user_agent: Client user agent of the exchange request.
        pending_mfa_store: Store for the MFA lockout and the TOTP replay guard.
        password_hasher: Hasher for the stored refresh token.
        token_manager: Token manager that signs the tokens.
        db: Database session.
        device_id: Device id from the browser's device cookie or the mobile app's ``X-Device-Id`` header, or None when
            the client sent no valid one.

    Returns:
        The tokens; web clients get the refresh token as a cookie in the outcome, mobile clients in the body. An SSO
        sign-in also carries the device id the client keeps: in the outcome for the browser's cookie, in the body for
        the mobile app.

    Raises:
        NotFoundError: If the session does not exist, has no OAuth state (an exchange that finished clears it), was
            created before a security change of the account, or another exchange claimed it first.
        InvalidInputError: If the OAuth state holds no PKCE data, the verifier does not match, or the client type
            differs from the one recorded when the sign-in started.
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
        raise core_exceptions.NotFoundError(_SESSION_NOT_ELIGIBLE_MESSAGE)

    session_obj, oauth_state = session_with_state
    if not oauth_state:
        logger.warning(
            "Token exchange failed: session <value_1> has no OAuth state",
            extra=core_logger.context(value_1=fingerprint),
        )
        raise core_exceptions.NotFoundError(_SESSION_NOT_ELIGIBLE_MESSAGE)
    if oauth_state.purpose != oauth_state_constants.OAuthStatePurpose.LOGIN:
        logger.warning(
            "Token exchange failed: session <value_1> belongs to a <purpose> flow, not a login",
            extra=core_logger.context(value_1=fingerprint, purpose=oauth_state.purpose),
        )
        raise core_exceptions.NotFoundError(_SESSION_NOT_ELIGIBLE_MESSAGE)

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
        _record_refusal(
            jasil_audit.Outcome.FAILURE, login_audit_actions.LoginFailureReason.PKCE_MISMATCH, session_obj.user_id
        )
        raise

    # The client type recorded when the sign-in started decides the response, so an exchange cannot switch between the
    # cookie-based web response and the body-only mobile response. A mismatch is refused like a wrong verifier.
    if client_type != oauth_state.client_type:
        logger.warning(
            "Token exchange client_type mismatch for session <value_1>: "
            "stored=<stored_client_type>, header=<header_client_type>",
            extra=core_logger.context(
                value_1=fingerprint, stored_client_type=oauth_state.client_type, header_client_type=client_type
            ),
        )
        _record_refusal(
            jasil_audit.Outcome.FAILURE, login_audit_actions.LoginFailureReason.PKCE_MISMATCH, session_obj.user_id
        )
        raise core_exceptions.InvalidInputError(_INVALID_VERIFIER_MESSAGE)

    user = users_integration.require_user(session_obj.user_id, db)
    try:
        users_integration.require_active_user(user)
    except core_exceptions.PermissionDeniedError:
        _record_refusal(jasil_audit.Outcome.DENIED, login_audit_actions.LoginFailureReason.INACTIVE, user.id)
        raise

    # Checked before an MFA code is tried, so a session that a security change outdated cannot be used to guess codes.
    # The lock it takes lasts until the exchange commits.
    if not security_generation_integration.matches_locked(user.id, oauth_state.security_generation, db):
        logger.warning(
            "Token exchange refused: the account's security changed after session <value_1> was created",
            extra=core_logger.context(value_1=fingerprint),
        )
        _record_refusal(jasil_audit.Outcome.FAILURE, login_audit_actions.LoginFailureReason.SECURITY_CHANGED, user.id)
        raise core_exceptions.NotFoundError(_SESSION_NOT_ELIGIBLE_MESSAGE)

    mfa_verified = oauth_state.idp_id is not None and mfa_integration.is_mfa_enabled_for_user(user.id, db)
    if mfa_verified:
        if mfa_code is None:
            logger.info(
                "Token exchange for session <value_1> needs an MFA code", extra=core_logger.context(value_1=fingerprint)
            )
            raise core_exceptions.MfaRequiredError()
        sso_method = login_audit_actions.LoginMethod.IDENTITY_PROVIDER
        authentication_service.refuse_while_mfa_locked_out(
            user.username, ip_address, user.id, sso_method, pending_mfa_store, device_id, db
        )
        authentication_service.require_valid_mfa_code(
            user.username, ip_address, user.id, sso_method, mfa_code, pending_mfa_store, password_hasher, db
        )
        try:
            pending_mfa_store.reset_attempts(user.username, ip_address, user_id=user.id)
        except lockout_contracts.AuthSecurityStoreUnavailableError as err:
            authentication_service.raise_auth_security_store_unavailable(err)

    # The session records the second factor the exchange verified next to the methods it was created with.
    amr = session_obj.amr
    if mfa_verified:
        amr = [*amr, auth_constants.AuthMethod.ONE_TIME_CODE, auth_constants.AuthMethod.MULTI_FACTOR]

    (_, access_token_exp, access_token, refresh_token_exp, refresh_token, csrf_token) = (
        authentication_token_service.create_tokens(
            user,
            session_obj.client_type,
            token_manager,
            server_settings_integration.get_session_policy(db),
            session_id,
        )
    )

    # Store the refresh-token hash, mark the tokens exchanged and extend the session from the end of the exchange
    # window to the refresh lifetime in one conditional update. The CSRF hash is not stored: the first /refresh
    # after a page reload establishes the binding.
    session_expires_at = sessions_integration.claim_session_for_token_exchange(
        session_id, password_hasher.hash_password(refresh_token), refresh_token_exp, amr, db
    )
    if session_expires_at is None:
        # Another exchange claimed the session first; to this caller it is the session of a finished exchange.
        logger.warning("Token exchange lost race for session <value_1>", extra=core_logger.context(value_1=fingerprint))
        raise core_exceptions.NotFoundError(_SESSION_NOT_ELIGIBLE_MESSAGE)
    issued_device_id = None
    if oauth_state.idp_id is not None:
        # An SSO sign-in is complete once its tokens are issued; a password sign-in was audited, and its device
        # recorded, when its session was created.
        sign_in = known_devices_integration.record_sign_in(
            user.id,
            device_id,
            ip_address,
            user_agent,
            known_devices_events.SignInMethod.IDENTITY_PROVIDER,
            db,
        )
        issued_device_id = sign_in.device_id
        sessions_integration.set_session_device_hash(session_id, core_hashing.sha256_hex(issued_device_id), db)
        with login_audit_integration.acting_as_user(user.id):
            jasil_audit.stage(
                db,
                login_audit_actions.LOGIN,
                **login_audit_integration.user_target(user.id),
                details=login_audit_actions.LoginDetails(
                    method=login_audit_actions.LoginMethod.IDENTITY_PROVIDER,
                    mfa=mfa_verified,
                    new_device=sign_in.new_device,
                ),
            )
    db.commit()

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
            session_id, access_token, access_token_exp, refresh_token, refresh_token_exp, session_expires_at, csrf_token
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
