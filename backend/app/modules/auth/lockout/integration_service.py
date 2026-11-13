"""Lockout primitives exposed to authentication stores."""

import uuid
from collections.abc import Callable

import jasil.audit as jasil_audit
from jasil.providers import StateProvider

import core.dependencies as core_dependencies
import core.logger as core_logger
import modules.auth.lockout.audit_actions as lockout_audit_actions
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.lockout_store as lockout_store

logger = core_logger.get_logger(__name__)


def new_progressive_lockout(
    state: StateProvider,
    *,
    name: str,
    tiers: tuple[lockout_contracts.LockoutTier, ...],
    attempts_ttl_seconds: int,
    normalize_key: Callable[[str], str] | None = None,
) -> lockout_contracts.LockoutStore:
    """Create a lockout counter bound to the caller's platform state provider.

    Args:
        state: Platform state provider that holds the counters.
        name: Key namespace of the counter.
        tiers: Failure thresholds with their lock duration and label, ascending.
        attempts_ttl_seconds: How long a failure counter is remembered.
        normalize_key: Canonical form applied to a key before it is hashed.

    Returns:
        The lockout counter.
    """
    return lockout_store.ProgressiveLockout(
        state,
        name=name,
        tiers=tiers,
        attempts_ttl_seconds=attempts_ttl_seconds,
        normalize_key=normalize_key,
    )


def new_step_up_account_lockout(state: StateProvider) -> lockout_contracts.LockoutStore:
    """Create the account-wide step-up failure counter, keyed by the user id as a string.

    Args:
        state: Platform state provider that holds the counter.

    Returns:
        The lockout counter.
    """
    return new_progressive_lockout(
        state,
        name="step_up_account",
        tiers=lockout_contracts.ACCOUNT_STEP_UP_LOCKOUT_TIERS,
        attempts_ttl_seconds=lockout_contracts.ACCOUNT_STEP_UP_ATTEMPTS_TTL_SECONDS,
    )


def clear_step_up_account_lockout(user_id: uuid.UUID) -> None:
    """Lift the account-wide step-up lock and failure count of a user after a recovery that proved ownership.

    A recovery that follows an outage of the shared state still succeeds; the lock then ends on its own.

    Args:
        user_id: The user whose account-wide failed step-ups are forgotten.
    """
    try:
        new_step_up_account_lockout(core_dependencies.get_platform_state()).reset_attempts(str(user_id))
    except lockout_contracts.AuthSecurityStoreUnavailableError:
        logger.warning("Account step-up lock was not cleared because the shared state is unavailable")


def normalize_username_key(username: str) -> str:
    """Return the canonical lockout key for a username.

    Args:
        username: Raw username from the request.

    Returns:
        The trimmed, lower-cased username, the form the account lookup matches on.
    """
    return lockout_store.normalize_username_key(username)


def username_log_identifier(username: str) -> str:
    """Return a non-reversible identifier suitable for security logs.

    Args:
        username: Raw username from the request.

    Returns:
        A stable hash-based identifier.
    """
    return lockout_store.username_log_identifier(username)


def report_lockout_applied(
    store_name: str,
    tiers: tuple[lockout_contracts.LockoutTier, ...],
    failed_attempts: int,
    *,
    username: str | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Log and audit that a failed attempt closed the lockout gate.

    A caller records a failure only while the key is not locked out, so a count at or above the first tier means this
    attempt applied a lockout. The counters live in the state provider, so the audit row is written on a transaction
    of its own. It never holds the username.

    Args:
        store_name: Which counter locked (``login``, ``login_account``, ``mfa``, ``mfa_account``, ``step_up`` or ``step_up_account``).
        tiers: The tiers of that counter.
        failed_attempts: The count returned by ``record_failed_attempt``.
        username: Username the counter is keyed on, when it is one; only its hash is logged.
        user_id: The account the counter protects, when the caller knows it; the audit row targets it.

    Raises:
        ValueError: If ``store_name`` is not a known counter.
    """
    if not tiers or failed_attempts < tiers[0][0]:
        return
    target = (
        {} if user_id is None else {"target_type": "user", "target_id": str(user_id), "target_owner_id": str(user_id)}
    )
    jasil_audit.record_detached(
        lockout_audit_actions.LOCKOUT_APPLY,
        outcome=jasil_audit.Outcome.SUCCESS,
        **target,
        details=lockout_audit_actions.LockoutApplyDetails(
            counter=lockout_audit_actions.LockoutCounter(store_name), failed_attempts=failed_attempts
        ),
    )
    logger.warning(
        "Progressive authentication lockout applied",
        extra=core_logger.context(
            store=store_name,
            username_hash=username_log_identifier(username) if username is not None else None,
            failed_attempts=failed_attempts,
        ),
    )
