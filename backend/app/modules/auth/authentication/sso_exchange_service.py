"""Exchange of a sign-in session and its PKCE verifier for tokens."""

from __future__ import annotations

import uuid

import jasil.audit as jasil_audit
from jasil.providers import StateProvider
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import core.network as core_network
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as authentication_service
import modules.auth.computation as auth_computation
import modules.auth.constants as auth_constants
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.login_audit.integration_service as login_audit_integration
import modules.auth.mfa.dependencies as mfa_dependencies
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.integration_service as sessions_integration
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
    session_id: uuid.UUID,
    code_verifier: str,
    client_type: auth_constants.ClientType,
    ip_address: str,
    user_agent: str,
    pending_mfa_store: mfa_dependencies.PendingMFAStore,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    *,
    device_id: str | None,
    state: StateProvider,
) -> auth_schema.AuthOutcome[auth_schema.SessionExchangeRead]:
    """Exchange a PKCE code verifier for the tokens of a session a sign-in created.

    The session was created by a mobile password sign-in or the identity-provider callback and holds no tokens yet.
    The caller proves it holds the verifier whose challenge the OAuth state stored; the exchange succeeds once per
    session; a second one finds the session without its OAuth state and is answered like an unknown session. The
    client type recorded when the sign-in started is the only one that can redeem it, and a different
    ``X-Client-Type`` is refused like a wrong verifier.

    A session that came from an identity provider also needs the account's second factor when the account has MFA
    enabled, since the provider's sign-in does not replace it. The exchange then answers the MFA step instead of the
    tokens and leaves the session unused: the challenge it issues is bound to this request's client type and client
    network and to the session's security generation, and ``/auth/mfa/verify`` claims the session with it. Another
    exchange of the session issues another challenge. A session from a password login has already passed MFA.

    Nothing the identity-provider callback staged for the account (a link by email, the profile sync) is written until
    the sign-in completes, here or at the MFA step, in the transaction that claims the session.

    Args:
        session_id: Session created by the sign-in.
        code_verifier: PKCE verifier sent by the client.
        client_type: ``X-Client-Type`` header of the exchange request.
        ip_address: Client address of the exchange request.
        user_agent: Client user agent of the exchange request.
        pending_mfa_store: Store for pending MFA logins.
        token_manager: Token manager that signs the tokens.
        db: Database session.
        device_id: Device id from the browser's device cookie or the mobile app's ``X-Device-Id`` header, or None when
            the client sent no valid one.
        state: The platform state provider, which holds what an identity-provider callback staged for the account.

    Returns:
        The tokens; web clients get the refresh token as a cookie in the outcome, mobile clients in the body. An SSO
        sign-in also carries the device id the client keeps: in the outcome for the browser's cookie, in the body for
        the mobile app. For an identity-provider session of an account with MFA, the MFA step instead.

    Raises:
        NotFoundError: If the session does not exist, has no OAuth state (an exchange that finished clears it), was
            created before a security change of the account, another exchange claimed it first, or what its callback
            staged can no longer be applied.
        InvalidInputError: If the OAuth state holds no PKCE data, the verifier does not match, or the client type
            differs from the one recorded when the sign-in started.
        PermissionDeniedError: If the account is no longer active.
        ServiceUnavailableError: If the pending-login store or the state store is down.
    """
    fingerprint = core_hashing.log_fingerprint(str(session_id))
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

    # Checked before an MFA challenge is issued, so a session that a security change outdated cannot start one. The
    # lock it takes lasts until the exchange commits.
    if not security_generation_integration.matches_locked(user.id, oauth_state.security_generation, db):
        logger.warning(
            "Token exchange refused: the account's security changed after session <value_1> was created",
            extra=core_logger.context(value_1=fingerprint),
        )
        _record_refusal(jasil_audit.Outcome.FAILURE, login_audit_actions.LoginFailureReason.SECURITY_CHANGED, user.id)
        raise core_exceptions.NotFoundError(_SESSION_NOT_ELIGIBLE_MESSAGE)

    if oauth_state.idp_id is not None and mfa_integration.is_mfa_enabled_for_user(user.id, db):
        logger.info(
            "Token exchange for session <value_1> continues to the MFA step",
            extra=core_logger.context(value_1=fingerprint),
        )
        return auth_schema.AuthOutcome(
            authentication_service.start_mfa_challenge(
                mfa_dependencies.PendingLogin(
                    user_id=user.id,
                    client_type=client_type,
                    code_challenge=None,
                    code_challenge_method=None,
                    client_network=core_network.client_network(ip_address),
                    security_generation=oauth_state.security_generation,
                    sso_session_id=session_id,
                ),
                pending_mfa_store,
                db,
            )
        )

    exchanged = authentication_service.complete_session_exchange(
        user,
        session_id,
        session_obj.client_type,
        session_obj.amr,
        ip_address,
        user_agent,
        token_manager,
        db,
        idp_id=oauth_state.idp_id,
        mfa=False,
        device_id=device_id,
        state=state,
    )
    if exchanged is None:
        # Another exchange claimed the session first, or what its identity-provider callback staged can no longer be
        # applied; to this caller it is a session that cannot be exchanged.
        if oauth_state.idp_id is not None:
            _record_refusal(
                jasil_audit.Outcome.FAILURE, login_audit_actions.LoginFailureReason.SSO_SESSION_ENDED, user.id
            )
        raise core_exceptions.NotFoundError(_SESSION_NOT_ELIGIBLE_MESSAGE)
    return auth_schema.AuthOutcome(exchanged.body, exchanged.refresh_cookie, device_id=exchanged.device_id)
