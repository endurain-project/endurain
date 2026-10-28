"""Lockout primitives exposed to authentication stores."""

from collections.abc import Callable

from jasil.providers import StateProvider

import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.lockout_store as lockout_store


def new_progressive_lockout(
    state: StateProvider,
    *,
    name: str,
    display_name: str,
    tiers: tuple[lockout_contracts.LockoutTier, ...],
    attempts_ttl_seconds: int,
    normalize_key: Callable[[str], str] | None = None,
) -> lockout_contracts.LockoutStore:
    """Create a lockout counter bound to the caller's platform state provider."""
    return lockout_store.ProgressiveLockout(
        state,
        name=name,
        display_name=display_name,
        tiers=tiers,
        attempts_ttl_seconds=attempts_ttl_seconds,
        normalize_key=normalize_key,
    )


def username_log_identifier(username: str) -> str:
    """Return a non-reversible identifier suitable for security logs."""
    return lockout_store.username_log_identifier(username)
