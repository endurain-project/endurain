"""Contracts shared by authentication lockout stores."""

from datetime import datetime
from typing import Protocol

import core.exceptions as core_exceptions

type LockoutTier = tuple[int, int, str]

LOGIN_LOCKOUT_TIERS: tuple[LockoutTier, ...] = ((5, 300, "5 min"), (10, 1800, "30 min"), (20, 86400, "24 hours"))
# Failures from every address against one account; far above LOGIN_LOCKOUT_TIERS so one client cannot reach it quickly.
ACCOUNT_LOGIN_LOCKOUT_TIERS: tuple[LockoutTier, ...] = ((50, 900, "15 min"),)
MFA_LOCKOUT_TIERS: tuple[LockoutTier, ...] = ((5, 300, "5 min"), (10, 1800, "30 min"), (15, 7200, "2 hours"))
STEP_UP_LOCKOUT_TIERS: tuple[LockoutTier, ...] = (
    (5, 300, "5 min"),
    (10, 1800, "30 min"),
    (15, 7200, "2 hours"),
)


class AuthSecurityStoreUnavailableError(core_exceptions.ServiceUnavailableError, RuntimeError):
    """Raised when shared authentication security storage is unavailable."""


class LockoutStore(Protocol):
    """Operations implemented by a progressive lockout counter."""

    def is_locked_out(self, key: str) -> bool:
        """Return whether the supplied key is currently locked out."""
        ...

    def get_lockout_time(self, key: str) -> datetime | None:
        """Return the active lockout expiry, if one exists."""
        ...

    def record_failed_attempt(self, key: str) -> int:
        """Record a failed attempt and return the updated count."""
        ...

    def reset_attempts(self, key: str) -> None:
        """Clear the failed-attempt count for the supplied key."""
        ...

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        ...
