"""Contracts shared by authentication lockout stores."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import core.exceptions as core_exceptions

type LockoutTier = tuple[int, int, str]

LOGIN_LOCKOUT_TIERS: tuple[LockoutTier, ...] = ((5, 300, "5 min"), (10, 1800, "30 min"), (20, 86400, "24 hours"))
# Failures in a row from every address against one account. The lock lasts 30 days and, like the count, is lifted by
# a successful sign-in, a password reset, a password change or an administrator setting the password.
ACCOUNT_LOGIN_LOCKOUT_TIERS: tuple[LockoutTier, ...] = ((100, 30 * 24 * 60 * 60, "30 days"),)
# How long the account-wide count survives without a new failure.
ACCOUNT_LOGIN_ATTEMPTS_TTL_SECONDS = 30 * 24 * 60 * 60
MFA_LOCKOUT_TIERS: tuple[LockoutTier, ...] = ((5, 300, "5 min"), (10, 1800, "30 min"), (15, 7200, "2 hours"))
# Wrong MFA codes in a row from every address against one account. The lock lasts 30 days and, like the count, is
# lifted by a successful MFA sign-in, the user turning MFA on or off, or an administrator resetting it.
ACCOUNT_MFA_LOCKOUT_TIERS: tuple[LockoutTier, ...] = ((100, 30 * 24 * 60 * 60, "30 days"),)
# How long the account-wide MFA count survives without a new wrong code.
ACCOUNT_MFA_ATTEMPTS_TTL_SECONDS = 30 * 24 * 60 * 60
STEP_UP_LOCKOUT_TIERS: tuple[LockoutTier, ...] = (
    (5, 300, "5 min"),
    (10, 1800, "30 min"),
    (15, 7200, "2 hours"),
)


@dataclass(frozen=True)
class FailureOutcome:
    """The result of recording one failure against a lockout counter.

    Attributes:
        count: The count after the failure.
        newly_locked: Whether this failure closed the gate.
    """

    count: int
    newly_locked: bool


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

    def record_failure(self, key: str) -> FailureOutcome:
        """Record a failed attempt and return the updated count with whether it closed the gate."""
        ...

    def reset_attempts(self, key: str) -> None:
        """Clear the failed-attempt count for the supplied key."""
        ...

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        ...
