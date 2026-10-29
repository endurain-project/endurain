"""Auth-owned step-up verification with progressive lockout."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NoReturn

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.account_security.step_up_store as account_security_step_up_store
import modules.auth.computation as auth_computation
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.identity_providers.schema as identity_providers_schema
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.mfa.integration_service as mfa_integration
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def _record_failure(step_up_store: account_security_step_up_store.StepUpStore, key: str) -> None:
    """Record a failed step-up attempt and report a lockout it applies.

    Args:
        step_up_store: Step-up lockout store.
        key: Lockout key of the user.
    """
    failed_attempts = step_up_store.record_failed_attempt(key)
    lockout_integration.report_lockout_applied("step_up", lockout_contracts.STEP_UP_LOCKOUT_TIERS, failed_attempts)


def _refuse_step_up(
    step_up_store: account_security_step_up_store.StepUpStore, key: str, user_id: int, detail: str
) -> NoReturn:
    """Record a failed step-up attempt, log it and refuse it.

    Args:
        step_up_store: Step-up lockout store.
        key: Lockout key of the user.
        user_id: Authenticated user ID, for the log.
        detail: Client-facing reason for the refusal.

    Raises:
        UnauthenticatedError: Always raised.
    """
    _record_failure(step_up_store, key)
    logger.warning(
        "Step-up refused for user <user_id>: <detail>", extra=core_logger.context(user_id=user_id, detail=detail)
    )
    raise core_exceptions.UnauthenticatedError(detail, scheme="Bearer")


def _step_up_key(user_id: int) -> str:
    """Build the lockout key for a user's step-up attempts.

    Args:
        user_id: Authenticated user ID.

    Returns:
        Stable string key for lockout tracking.

    Raises:
        None.
    """
    return f"user:{user_id}"


def _raise_if_locked_out(step_up_store: account_security_step_up_store.StepUpStore, key: str, user_id: int) -> None:
    """Refuse the attempt while the user is locked out.

    Args:
        step_up_store: Step-up lockout store.
        key: Lockout key of the user.
        user_id: Authenticated user ID, for the log.

    Raises:
        TooManyRequestsError: When the user is locked out, with ``Retry-After`` set when the end is known.
    """
    if step_up_store.is_locked_out(key):
        lockout_until = step_up_store.get_lockout_time(key)
        logger.warning("Step-up blocked for user <user_id>: locked out", extra=core_logger.context(user_id=user_id))
        error = core_exceptions.TooManyRequestsError(
            "Too many failed step-up attempts. Try again later.", retry_at=lockout_until
        )
        if lockout_until is not None:
            retry_after = max(0, int((lockout_until - datetime.now(UTC)).total_seconds()))
            error.headers = {"Retry-After": str(retry_after)}
        raise error


def require_not_locked_out(user_id: int, step_up_store: account_security_step_up_store.StepUpStore) -> None:
    """Refuse to start a step-up while the user is locked out of step-up attempts.

    Args:
        user_id: ID of the authenticated user.
        step_up_store: Step-up lockout store.

    Raises:
        TooManyRequestsError: When the user is locked out.
    """
    _raise_if_locked_out(step_up_store, _step_up_key(user_id), user_id)


def verify_step_up_credentials(
    user_id: int,
    current_password: str | None,
    mfa_code: str | None,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
    *,
    idp_reauth: identity_providers_schema.IdpReauthProof | None = None,
    session_id: str | None = None,
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

    Failed verifications are tracked per-user with progressive lockout: 5 failures → 5 min, 10 → 30 min,
    15 → 2 hours. Lockout is checked before any comparison so that guessing is bounded even when the attacker
    has a valid access token. A password-less request that carries no ticket at all is the challenge, not a
    failure, and is not counted.

    Args:
        user_id: ID of the authenticated user.
        current_password: The user's current password, for an account that has one.
        mfa_code: TOTP or backup code, required when MFA is enabled. Ignored when MFA is disabled.
        step_up_store: Step-up lockout, TOTP replay and ticket store.
        db: SQLAlchemy database session.
        idp_reauth: Proof of a fresh identity-provider sign-in, for an account without a local password.
        session_id: The caller's session; a ticket is valid only in the session that started it. An operation
            only an account with a password can perform (a password change) passes none.
        action: The operation being authorised; a ticket is valid only for the operation it was issued for.
            ``None`` likewise for an operation no ticket can authorise.

    Raises:
        TooManyRequestsError: If the user is currently locked out.
        IdpReauthRequiredError: If the account has no local password and the request carried no ticket.
        UnauthenticatedError: If the password, the ticket or the MFA code is missing or wrong.
    """
    key = _step_up_key(user_id)

    _raise_if_locked_out(step_up_store, key, user_id)

    # Guard: ensure the user exists (raises 404 otherwise).
    users_integration.require_user(user_id, db)

    ticket: identity_providers_contracts.StepUpTicket | None = None
    password_hash = credentials_integration.get_password_hash(user_id, db)
    if password_hash is not None:
        if not current_password:
            _refuse_step_up(step_up_store, key, user_id, "Step-up verification failed")
        if not credentials_integration.verify_password(current_password, password_hash):
            _refuse_step_up(step_up_store, key, user_id, "Step-up verification failed")
    else:
        if idp_reauth is None:
            logger.info(
                "Step-up for user <user_id> needs a fresh identity-provider sign-in",
                extra=core_logger.context(user_id=user_id, action=action),
            )
            raise core_exceptions.IdpReauthRequiredError(identity_providers_constants.STEP_UP_MAX_AGE_SECONDS)
        ticket = step_up_store.read_ticket(idp_reauth.ticket)
        if not _ticket_matches(ticket, idp_reauth.code_verifier, user_id, session_id, action):
            _refuse_step_up(step_up_store, key, user_id, "Step-up verification failed")

    if mfa_integration.is_mfa_enabled_for_user(user_id, db):
        if not mfa_code:
            _refuse_step_up(step_up_store, key, user_id, "MFA code required for this operation")
        if not mfa_integration.verify_user_mfa(
            user_id, mfa_code, credentials_integration, db, replay_guard=step_up_store
        ):
            _refuse_step_up(step_up_store, key, user_id, "Step-up verification failed")

    # The ticket pays for one request: of two that raced past the checks above, only one redeems it.
    if ticket is not None and step_up_store.redeem_ticket(idp_reauth.ticket) != ticket:
        _refuse_step_up(step_up_store, key, user_id, "Step-up verification failed")

    # All factors passed — reset the failure counter.
    step_up_store.reset_attempts(key)


def _ticket_matches(
    ticket: identity_providers_contracts.StepUpTicket | None,
    code_verifier: str,
    user_id: int,
    session_id: str | None,
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
    if session_id is None or action is None:
        return False
    if ticket is None or ticket.user_id != user_id or ticket.session_id != session_id or ticket.action != action:
        return False
    try:
        auth_computation.validate_pkce_verifier(code_verifier, ticket.code_challenge, "S256")
    except core_exceptions.InvalidInputError:
        return False
    return True


def verify_mfa_code(
    user_id: int,
    mfa_code: str,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
) -> bool:
    """Check an MFA code under the step-up lockout, so a stolen access token cannot guess it freely.

    Failures share the user's step-up budget: a guess here and a guess at a sensitive operation draw from
    the same lockout.

    Args:
        user_id: ID of the authenticated user.
        mfa_code: TOTP or backup code to check.
        step_up_store: Step-up lockout store, which also records the accepted TOTP step.
        db: SQLAlchemy database session.

    Returns:
        True when the code is valid.

    Raises:
        TooManyRequestsError: When the user is locked out.
    """
    key = _step_up_key(user_id)
    _raise_if_locked_out(step_up_store, key, user_id)
    if not mfa_integration.verify_user_mfa(user_id, mfa_code, credentials_integration, db, replay_guard=step_up_store):
        _record_failure(step_up_store, key)
        logger.warning("MFA code refused for user <user_id>", extra=core_logger.context(user_id=user_id))
        return False
    step_up_store.reset_attempts(key)
    return True
