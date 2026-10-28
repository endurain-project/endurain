"""Shared-state store for failed password login attempts."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from jasil.providers import StateProvider

import core.dependencies as core_dependencies
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration


@runtime_checkable
class FailedLoginStore(Protocol):
    """Operations supported by the failed-login lockout store."""

    def is_locked_out(self, username: str) -> bool:
        """Return whether the supplied key is currently locked out."""
        ...

    def get_lockout_time(self, username: str) -> datetime | None:
        """Return the active lockout expiry, if one exists."""
        ...

    def record_failed_attempt(self, username: str) -> int:
        """Record a failed attempt and return the updated count."""
        ...

    def reset_attempts(self, username: str) -> None:
        """Clear the failed-attempt count for the supplied key."""
        ...

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        ...


class FailedLoginAttempts:
    """Track failed logins using the shared platform state provider."""

    def __init__(self, state: StateProvider) -> None:
        """Bind failed-login tracking to the shared platform state provider."""
        self._lockout = lockout_integration.new_progressive_lockout(
            state,
            name="login",
            tiers=lockout_contracts.LOGIN_LOCKOUT_TIERS,
            attempts_ttl_seconds=24 * 60 * 60,
            normalize_key=lockout_integration.normalize_username_key,
        )

    def is_locked_out(self, username: str) -> bool:
        """Check if a username is locked out."""
        return self._lockout.is_locked_out(username)

    def get_lockout_time(self, username: str) -> datetime | None:
        """Return the lockout expiry, if any."""
        return self._lockout.get_lockout_time(username)

    def record_failed_attempt(self, username: str) -> int:
        """Record a failed login and return the current attempt count."""
        return self._lockout.record_failed_attempt(username)

    def reset_attempts(self, username: str) -> None:
        """Clear the failed-login counter."""
        self._lockout.reset_attempts(username)

    def clear_all(self) -> None:
        """Clear all failed-login records."""
        self._lockout.clear_all()


def get_failed_login_attempts(
    state: core_dependencies.PlatformState,
) -> FailedLoginStore:
    """Provide a failed-login store bound to the active platform state."""
    return FailedLoginAttempts(state)
