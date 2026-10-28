"""Contracts shared by authentication lockout stores."""

from datetime import datetime
from typing import Protocol

type LockoutTier = tuple[int, int, str]

LOGIN_LOCKOUT_TIERS: tuple[LockoutTier, ...] = ((5, 300, "5 min"), (10, 1800, "30 min"), (20, 86400, "24 hours"))
MFA_LOCKOUT_TIERS: tuple[LockoutTier, ...] = ((5, 300, "5 min"), (10, 1800, "30 min"), (15, 7200, "2 hours"))
STEP_UP_LOCKOUT_TIERS: tuple[LockoutTier, ...] = (
    (5, 300, "5 min"),
    (10, 1800, "30 min"),
    (15, 7200, "2 hours"),
)


class AuthSecurityStoreUnavailableError(RuntimeError):
    """Raised when shared authentication security storage is unavailable."""


class LockoutStore(Protocol):
    """Operations implemented by a progressive lockout counter."""

    def is_locked_out(self, key: str) -> bool: ...

    def get_lockout_time(self, key: str) -> datetime | None: ...

    def record_failed_attempt(self, key: str) -> int: ...

    def reset_attempts(self, key: str) -> None: ...

    def clear_all(self) -> None: ...
