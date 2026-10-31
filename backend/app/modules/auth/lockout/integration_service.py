"""Lockout primitives exposed to authentication stores."""

from collections.abc import Callable

from jasil.providers import StateProvider

import core.logger as core_logger
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


def normalize_username_key(username: str) -> str:
    """Return the canonical lockout key for a username.

    Args:
        username: Raw username from the request.

    Returns:
        The URL-decoded, trimmed, case-folded username.
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
) -> None:
    """Log that a failed attempt closed the lockout gate.

    A caller records a failure only while the key is not locked out, so a count at or above the first tier means this
    attempt applied a lockout.

    Args:
        store_name: Which counter locked (``login``, ``mfa`` or ``step_up``).
        tiers: The tiers of that counter.
        failed_attempts: The count returned by ``record_failed_attempt``.
        username: Username the counter is keyed on, when it is one.
    """
    if not tiers or failed_attempts < tiers[0][0]:
        return
    logger.warning(
        "Progressive authentication lockout applied",
        extra=core_logger.context(
            store=store_name,
            username_hash=username_log_identifier(username) if username is not None else None,
            failed_attempts=failed_attempts,
        ),
    )
