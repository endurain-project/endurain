"""Auth-owned step-up verification with progressive lockout."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.account_security.step_up_store as account_security_step_up_store
import modules.auth.credentials.integration_service as auth_credentials_crud
import modules.auth.mfa.integration_service as mfa_integration
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


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


def verify_step_up_credentials(
    user_id: int,
    current_password: str | None,
    mfa_code: str | None,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
) -> None:
    """Enforce step-up verification for sensitive account operations.

    A valid access token alone is not sufficient authorisation for
    operations that grant persistent account access (password
    change, API-key creation, MFA enrolment, MFA backup-code
    regeneration, MFA disable, etc.). This function requires the
    caller to re-prove possession of the current password and —
    when MFA is enabled — a fresh TOTP or backup code.

    SSO-only accounts have no local password (no row in
    ``users_local_credentials``). For those callers the password
    factor is skipped because there is nothing to verify against. The
    correct fix is to require a fresh IdP re-authentication for
    SSO-only accounts; this is not yet implemented.
    TODO(issue): create and link a tracker issue for fresh IdP
    re-auth on SSO-only step-up. Documented in
    ``docs/developer-guide/auth-boundary.md``.

    Failed verifications are tracked per-user with progressive
    lockout: 5 failures → 5 min, 10 → 30 min, 15 → 2 hours.
    Lockout is checked before any password or MFA comparison so
    that incorrect-guess enumeration is bounded even when the
    attacker has a valid access token.

    Args:
        user_id: ID of the authenticated user.
        current_password: The user's current password as supplied
            in the request body. May be ``None`` for SSO-only
            accounts.
        mfa_code: TOTP or backup code, required when MFA is
            enabled. Ignored when MFA is disabled.
        step_up_store: Step-up lockout store.
        db: SQLAlchemy database session.

    Returns:
        None.

    Raises:
        DomainError: 429 if the user is currently locked out;
            401 if the current password is wrong, is missing for
            an account that has one, or when MFA is enabled and
            the supplied code is missing or invalid.
    """
    key = _step_up_key(user_id)

    if step_up_store.is_locked_out(key):
        lockout_until = step_up_store.get_lockout_time(key)
        logger.warning(f"Step-up blocked for user {user_id}: locked out")
        error = core_exceptions.TooManyRequestsError(
            "Too many failed step-up attempts. Try again later.", retry_at=lockout_until
        )
        if lockout_until is not None:
            retry_after = max(0, int((lockout_until - datetime.now(UTC)).total_seconds()))
            error.headers = {"Retry-After": str(retry_after)}
        raise error

    # Guard: ensure the user exists (raises 404 otherwise).
    users_integration.require_user(user_id, db)

    password_hash = auth_credentials_crud.get_password_hash(user_id, db)
    if password_hash is not None:
        if not current_password:
            step_up_store.record_failed_attempt(key)
            raise core_exceptions.UnauthenticatedError("Step-up verification failed", scheme="Bearer")
        if not auth_credentials_crud.verify_password(current_password, password_hash):
            step_up_store.record_failed_attempt(key)
            raise core_exceptions.UnauthenticatedError("Step-up verification failed", scheme="Bearer")
    # else: SSO-only account; no password to verify. See docstring
    # and docs/developer-guide/auth-boundary.md "Known Structural Debt".

    if mfa_integration.is_mfa_enabled_for_user(user_id, db):
        if not mfa_code:
            step_up_store.record_failed_attempt(key)
            raise core_exceptions.UnauthenticatedError("MFA code required for this operation", scheme="Bearer")
        if not mfa_integration.verify_user_mfa(user_id, mfa_code, auth_credentials_crud, db):
            step_up_store.record_failed_attempt(key)
            raise core_exceptions.UnauthenticatedError("Step-up verification failed", scheme="Bearer")

    # All factors passed — reset the failure counter.
    step_up_store.reset_attempts(key)
