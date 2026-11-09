"""Auth-owned step-up verification with progressive lockout."""

from __future__ import annotations

from typing import NoReturn

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.account_security.step_up_store as account_security_step_up_store
import modules.auth.computation as auth_computation
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.schema as auth_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def _record_refusal(
    user_id: int,
    method: login_audit_actions.StepUpMethod,
    reason: login_audit_actions.StepUpFailureReason,
) -> None:
    """Record a refused step-up on a session of its own, since the request answers with an error.

    Args:
        user_id: Authenticated user ID.
        method: How the re-authentication was attempted.
        reason: Why it was refused.
    """
    locked_out = reason == login_audit_actions.StepUpFailureReason.LOCKED_OUT
    jasil_audit.record_detached(
        login_audit_actions.STEP_UP_VERIFY,
        outcome=jasil_audit.Outcome.DENIED if locked_out else jasil_audit.Outcome.FAILURE,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=login_audit_actions.StepUpDetails(method=method, reason=reason),
    )


def _record_failure(step_up_store: account_security_step_up_store.StepUpStore, key: str, user_id: int) -> None:
    """Record a failed step-up attempt and report a lockout it applies.

    Args:
        step_up_store: Step-up lockout store.
        key: Lockout key of the user and session.
        user_id: Authenticated user ID, whom a lockout is audited against.
    """
    failed_attempts = step_up_store.record_failed_attempt(key)
    lockout_integration.report_lockout_applied(
        "step_up", lockout_contracts.STEP_UP_LOCKOUT_TIERS, failed_attempts, user_id=user_id
    )


def _refuse_step_up(
    step_up_store: account_security_step_up_store.StepUpStore,
    key: str,
    user_id: int,
    method: login_audit_actions.StepUpMethod,
    reason: str,
) -> NoReturn:
    """Record a failed step-up attempt, log it and refuse it with the one answer every failure gets.

    Args:
        step_up_store: Step-up lockout store.
        key: Lockout key of the user and session.
        user_id: Authenticated user ID, for the log.
        method: How the re-authentication was attempted.
        reason: Which check failed, for the log only; the client never sees it.

    Raises:
        StepUpFailedError: Always raised.
    """
    _record_failure(step_up_store, key, user_id)
    _record_refusal(user_id, method, login_audit_actions.StepUpFailureReason.INVALID_CREDENTIALS)
    logger.warning(
        "Step-up refused for user <user_id>: <reason>", extra=core_logger.context(user_id=user_id, reason=reason)
    )
    raise core_exceptions.StepUpFailedError()


def _step_up_key(user_id: int, session_id: str) -> str:
    """Build the lockout key for the step-up attempts of one session of a user.

    The key names the session, so failures made with one session never lock the user's other sessions out.

    Args:
        user_id: Authenticated user ID.
        session_id: The caller's session.

    Returns:
        Stable string key for lockout tracking.
    """
    return f"user:{user_id}:session:{session_id}"


def _raise_if_locked_out(
    step_up_store: account_security_step_up_store.StepUpStore,
    key: str,
    user_id: int,
    method: login_audit_actions.StepUpMethod,
) -> None:
    """Refuse the attempt while the session is locked out.

    Args:
        step_up_store: Step-up lockout store.
        key: Lockout key of the user and session.
        user_id: Authenticated user ID, for the log.
        method: How the re-authentication was being attempted.

    Raises:
        TooManyRequestsError: When the session is locked out, with ``Retry-After`` set when the end is known.
    """
    if step_up_store.is_locked_out(key):
        lockout_until = step_up_store.get_lockout_time(key)
        logger.warning("Step-up blocked for user <user_id>: locked out", extra=core_logger.context(user_id=user_id))
        _record_refusal(user_id, method, login_audit_actions.StepUpFailureReason.LOCKED_OUT)
        raise core_exceptions.TooManyRequestsError(
            "Too many failed step-up attempts. Try again later.", retry_at=lockout_until
        )


def require_not_locked_out(
    user_id: int, session_id: str, step_up_store: account_security_step_up_store.StepUpStore
) -> None:
    """Refuse to start a step-up while the session is locked out of step-up attempts.

    Args:
        user_id: ID of the authenticated user.
        session_id: The caller's session.
        step_up_store: Step-up lockout store.

    Raises:
        TooManyRequestsError: When the session is locked out.
    """
    _raise_if_locked_out(
        step_up_store, _step_up_key(user_id, session_id), user_id, login_audit_actions.StepUpMethod.IDENTITY_PROVIDER
    )


def verify_step_up_credentials(
    user_id: int,
    current_password: str | None,
    mfa_code: str | None,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
    *,
    session_id: str,
    idp_reauth: auth_schema.IdpReauthProof | None = None,
    action: identity_providers_constants.StepUpAction | None = None,
) -> None:
    """Enforce step-up verification for sensitive account operations.

    A valid access token alone is not sufficient authorisation for operations that grant persistent account
    access (API-key creation, MFA enrolment, identity-provider links, email change, account deletion, etc.).
    The caller re-proves their identity with a first factor and, when MFA is enabled, a fresh TOTP or backup
    code:

    - an account with a local password proves it with the password;
    - an account without one (signed up through an identity provider) proves a fresh sign-in with a linked
      provider: a single-use ticket the provider's callback issued for this user, this session and this
      operation, together with the PKCE verifier only the browser that started the sign-in holds.

    The ticket is checked first and redeemed only after every factor passed, so a wrong MFA code does not cost
    the user another trip through the provider.

    Failed verifications are tracked per user and session with progressive lockout: 5 failures → 5 min, 10 → 30 min,
    15 → 2 hours. Lockout is checked before any comparison so that guessing is bounded even when the attacker
    has a valid access token. A session that has failed does not lock the user's other sessions out, so a stolen
    session cannot lock the owner out. A password-less request that carries no ticket at all is the challenge, not a
    failure, and is not counted.

    Args:
        user_id: ID of the authenticated user.
        current_password: The user's current password, for an account that has one.
        mfa_code: TOTP or backup code, required when MFA is enabled. Ignored when MFA is disabled.
        step_up_store: Step-up lockout, TOTP replay and ticket store.
        db: SQLAlchemy database session.
        idp_reauth: Proof of a fresh identity-provider sign-in, for an account without a local password.
        session_id: The caller's session, which owns the lockout counter; a ticket is valid only in the session
            that started it.
        action: The operation being authorised; a ticket is valid only for the operation it was issued for.
            ``None`` for an operation no ticket can authorise (a password change).

    Raises:
        TooManyRequestsError: If the session is currently locked out.
        IdpReauthRequiredError: If the account has no local password and the request carried no ticket.
        StepUpFailedError: If the password, the ticket or the MFA code is missing or wrong; the answer is the
            same whichever it was.
    """
    key = _step_up_key(user_id, session_id)

    _raise_if_locked_out(step_up_store, key, user_id, login_audit_actions.StepUpMethod.UNSPECIFIED)

    # Guard: ensure the user exists (raises 404 otherwise).
    users_integration.require_user(user_id, db)

    ticket: identity_providers_contracts.StepUpTicket | None = None
    password_hash = credentials_integration.get_password_hash(user_id, db)
    if password_hash is not None:
        if not current_password:
            _refuse_step_up(
                step_up_store,
                key,
                user_id,
                login_audit_actions.StepUpMethod.PASSWORD,
                "no password sent",
            )
        password_verified, _ = credentials_integration.verify_and_update_password(
            current_password, password_hash, credentials_integration.get_password_hasher()
        )
        if not password_verified:
            _refuse_step_up(
                step_up_store,
                key,
                user_id,
                login_audit_actions.StepUpMethod.PASSWORD,
                "wrong password",
            )
    else:
        if idp_reauth is None:
            logger.info(
                "Step-up for user <user_id> needs a fresh identity-provider sign-in",
                extra=core_logger.context(user_id=user_id, action=action),
            )
            raise core_exceptions.IdpReauthRequiredError(identity_providers_constants.STEP_UP_MAX_AGE_SECONDS)
        ticket = step_up_store.read_ticket(idp_reauth.ticket)
        if not _ticket_matches(ticket, idp_reauth.code_verifier, user_id, session_id, action):
            _refuse_step_up(
                step_up_store,
                key,
                user_id,
                login_audit_actions.StepUpMethod.IDENTITY_PROVIDER,
                "ticket does not match",
            )

    if mfa_integration.is_mfa_enabled_for_user(user_id, db):
        if not mfa_code:
            _refuse_step_up(
                step_up_store,
                key,
                user_id,
                login_audit_actions.StepUpMethod.MFA_CODE,
                "no MFA code sent",
            )
        if not mfa_integration.verify_user_mfa(
            user_id, mfa_code, credentials_integration.get_password_hasher(), db, replay_guard=step_up_store
        ):
            _refuse_step_up(
                step_up_store,
                key,
                user_id,
                login_audit_actions.StepUpMethod.MFA_CODE,
                "wrong MFA code",
            )

    # The ticket pays for one request: of two that raced past the checks above, only one redeems it.
    if idp_reauth is not None and ticket is not None and step_up_store.redeem_ticket(idp_reauth.ticket) != ticket:
        _refuse_step_up(
            step_up_store,
            key,
            user_id,
            login_audit_actions.StepUpMethod.IDENTITY_PROVIDER,
            "ticket already redeemed",
        )

    # All factors passed — reset the failure counter.
    step_up_store.reset_attempts(key)


def _ticket_matches(
    ticket: identity_providers_contracts.StepUpTicket | None,
    code_verifier: str,
    user_id: int,
    session_id: str,
    action: identity_providers_constants.StepUpAction | None,
) -> bool:
    """Tell whether a step-up ticket was issued for this user, session and operation, to this browser.

    Args:
        ticket: The stored ticket, if it exists.
        code_verifier: The PKCE verifier the request sent.
        user_id: The authenticated user.
        session_id: The caller's session.
        action: The operation being authorised.

    Returns:
        True when the ticket exists, matches all three, and the verifier hashes to its challenge.
    """
    if action is None:
        return False
    if ticket is None or ticket.user_id != user_id or ticket.session_id != session_id or ticket.action != action:
        return False
    try:
        auth_computation.validate_pkce_verifier(code_verifier, ticket.code_challenge, "S256")
    except core_exceptions.InvalidInputError:
        return False
    return True
