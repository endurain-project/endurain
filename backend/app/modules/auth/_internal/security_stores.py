"""Authentication security stores for login and MFA lockout.

Pending-login bookkeeping and progressive lockout counters are kept in the
platform ``StateProvider`` (an in-process dict under ``local``, Redis under
``distributed``). The atomic increment-and-lock step is delegated to
``StateProvider.record_tiered_failure`` — a single call that both backends
implement atomically — so this module no longer contains any Redis code or a
memory-vs-Redis split.
"""

from collections.abc import Callable
from datetime import datetime
from typing import NoReturn, Protocol, runtime_checkable
from urllib.parse import unquote

import jasil.runtime as platform_runtime
from jasil.providers import StateBackendUnavailableError, StateProvider

import core.logger as core_logger
import modules.auth.lockout.contracts as auth_lockout_contracts
import modules.auth.lockout.integration_service as auth_lockout_integration

logger = core_logger.get_logger(__name__)

AuthSecurityStoreUnavailableError = auth_lockout_contracts.AuthSecurityStoreUnavailableError


def _raise_store_unavailable(operation: str, err: StateBackendUnavailableError) -> NoReturn:
    """
    Log a storage outage and re-raise it as an auth-security-store error.

    Args:
        operation: Storage operation that failed.
        err: The provider outage error.

    Raises:
        AuthSecurityStoreUnavailableError: Always raised.
    """
    logger.error(f"Auth security storage failed: {operation}", exc_info=err)
    raise AuthSecurityStoreUnavailableError("auth security storage is unavailable") from err


def normalize_username_key(username: str) -> str:
    """Normalise a username for security-store keys.

    Lockout counters must key on the same canonical form regardless of
    casing, surrounding whitespace, or URL-encoded variants supplied by
    the client.

    Args:
        username: Raw username string from the request.

    Returns:
        Canonical key suitable for lockout stores.

    Raises:
        None.
    """
    return unquote(username).replace("+", " ").strip().casefold()


def username_log_identifier(username: str) -> str:
    """Build a non-reversible username identifier for logs."""
    return auth_lockout_integration.username_log_identifier(username)


@runtime_checkable
class FailedLoginStore(Protocol):
    """Contract for failed-login lockout stores. Keys are usernames."""

    def is_locked_out(self, username: str) -> bool: ...

    def get_lockout_time(self, username: str) -> datetime | None: ...

    def record_failed_attempt(self, username: str) -> int: ...

    def reset_attempts(self, username: str) -> None: ...

    def clear_all(self) -> None: ...


@runtime_checkable
class StepUpStore(Protocol):
    """Contract for step-up lockout stores. Keys are stable user identifiers."""

    def is_locked_out(self, key: str) -> bool: ...

    def get_lockout_time(self, key: str) -> datetime | None: ...

    def record_failed_attempt(self, key: str) -> int: ...

    def reset_attempts(self, key: str) -> None: ...

    def clear_all(self) -> None: ...


# Progressive-lockout thresholds. Each entry is ``(failed_count_threshold,
# lockout_seconds, duration_label)`` in ascending order; the highest matched
# threshold wins.
_LOGIN_LOCKOUT_THRESHOLDS = auth_lockout_contracts.LOGIN_LOCKOUT_TIERS
_STEP_UP_LOCKOUT_THRESHOLDS = auth_lockout_contracts.STEP_UP_LOCKOUT_TIERS


class _ProgressiveLockout:
    """Bind a lockout configuration to the active state provider on first use."""

    def __init__(
        self,
        get_state: Callable[[], StateProvider],
        name: str,
        display_name: str,
        thresholds: tuple[tuple[int, int, str], ...],
        attempts_ttl_seconds: int,
        normalize_key: Callable[[str], str] | None = None,
    ) -> None:
        self._get_state = get_state
        self._name = name
        self._display_name = display_name
        self._thresholds = thresholds
        self._attempts_ttl_seconds = attempts_ttl_seconds
        self._normalize = normalize_key
        self._lockout: auth_lockout_contracts.LockoutStore | None = None

    def _provider(self) -> auth_lockout_contracts.LockoutStore:
        if self._lockout is None:
            self._lockout = auth_lockout_integration.new_progressive_lockout(
                self._get_state(),
                name=self._name,
                display_name=self._display_name,
                tiers=self._thresholds,
                attempts_ttl_seconds=self._attempts_ttl_seconds,
                normalize_key=self._normalize,
            )
        return self._lockout

    def is_locked_out(self, key: str) -> bool:
        return self._provider().is_locked_out(key)

    def get_lockout_time(self, key: str) -> datetime | None:
        return self._provider().get_lockout_time(key)

    def record_failed_attempt(self, key: str) -> int:
        return self._provider().record_failed_attempt(key)

    def reset_attempts(self, key: str) -> None:
        self._provider().reset_attempts(key)

    def clear_all(self) -> None:
        self._provider().clear_all()


class FailedLoginAttempts:
    """
    Track failed login attempts with progressive lockout (5/10/20 → 5m/30m/24h).

    Attributes:
        _state_override: Explicit provider (tests); ``None`` resolves the
            process-wide provider lazily at call time.
        _lockout: Shared progressive-lockout helper.
    """

    def __init__(self, state: StateProvider | None = None) -> None:
        self._state_override = state
        self._lockout = _ProgressiveLockout(
            self._get_state,
            name="login",
            display_name="Login",
            thresholds=_LOGIN_LOCKOUT_THRESHOLDS,
            attempts_ttl_seconds=24 * 60 * 60,
            normalize_key=normalize_username_key,
        )

    def _get_state(self) -> StateProvider:
        return self._state_override if self._state_override is not None else platform_runtime.get_state()

    def is_locked_out(self, username: str) -> bool:
        """Check if a username is locked out from failed logins."""
        return self._lockout.is_locked_out(username)

    def get_lockout_time(self, username: str) -> datetime | None:
        """Get the lockout expiry for a username, if locked out."""
        return self._lockout.get_lockout_time(username)

    def record_failed_attempt(self, username: str) -> int:
        """Record a failed login and return the current attempt count."""
        return self._lockout.record_failed_attempt(username)

    def reset_attempts(self, username: str) -> None:
        """Clear the failed-attempt counter on successful login."""
        self._lockout.reset_attempts(username)

    def clear_all(self) -> None:
        """Clear all failed-login records."""
        self._lockout.clear_all()


class StepUpAttempts:
    """
    Track failed step-up verification attempts (5/10/15 → 5m/30m/2h).

    Keys are stable user identifiers (e.g. ``user:{user_id}``).

    Attributes:
        _state_override: Explicit provider (tests); ``None`` resolves lazily.
        _lockout: Shared progressive-lockout helper.
    """

    def __init__(self, state: StateProvider | None = None) -> None:
        self._state_override = state
        self._lockout = _ProgressiveLockout(
            self._get_state,
            name="step_up",
            display_name="Step-up",
            thresholds=_STEP_UP_LOCKOUT_THRESHOLDS,
            attempts_ttl_seconds=2 * 60 * 60,
        )

    def _get_state(self) -> StateProvider:
        return self._state_override if self._state_override is not None else platform_runtime.get_state()

    def is_locked_out(self, key: str) -> bool:
        """Check if a user key is locked out from step-up."""
        return self._lockout.is_locked_out(key)

    def get_lockout_time(self, key: str) -> datetime | None:
        """Get the step-up lockout expiry for a user key, if locked out."""
        return self._lockout.get_lockout_time(key)

    def record_failed_attempt(self, key: str) -> int:
        """Record a failed step-up attempt and return the current count."""
        return self._lockout.record_failed_attempt(key)

    def reset_attempts(self, key: str) -> None:
        """Reset the step-up failure counter for a user key."""
        self._lockout.reset_attempts(key)

    def clear_all(self) -> None:
        """Clear all step-up failure records."""
        self._lockout.clear_all()


failed_login_attempts: FailedLoginStore = FailedLoginAttempts()
step_up_attempts: StepUpStore = StepUpAttempts()


def get_failed_login_attempts() -> FailedLoginStore:
    """Dependency injection for failed-login attempt storage."""
    return failed_login_attempts


def get_step_up_attempts() -> StepUpStore:
    """Dependency injection for step-up attempt tracking."""
    return step_up_attempts
