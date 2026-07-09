"""Authentication security stores for login and MFA lockout.

Pending-login bookkeeping and progressive lockout counters are kept in the
platform ``StateProvider`` (an in-process dict under ``local``, Redis under
``distributed``). The atomic increment-and-lock step is delegated to
``StateProvider.record_tiered_failure`` — a single call that both backends
implement atomically — so this module no longer contains any Redis code or a
memory-vs-Redis split.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import NoReturn, Protocol, runtime_checkable
from urllib.parse import unquote

import core.hashing as core_hashing
import core.logger as core_logger
import core.platform.runtime as platform_runtime
from core.platform.providers import StateBackendUnavailableError, StateProvider

_AUTH_KEY_PREFIX = "endurain:auth"


class AuthSecurityStoreUnavailableError(RuntimeError):
    """
    Raised when auth security storage cannot be reached.

    Attributes:
        None.
    """


def _raise_store_unavailable(operation: str, err: StateBackendUnavailableError) -> NoReturn:
    """
    Log a storage outage and re-raise it as an auth-security-store error.

    Args:
        operation: Storage operation that failed.
        err: The provider outage error.

    Raises:
        AuthSecurityStoreUnavailableError: Always raised.
    """
    core_logger.print_to_log(f"Auth security storage failed: {operation}", "error", exc=err)
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


def _username_digest(username: str) -> str:
    """
    Hash a normalized username for storage key names.

    Args:
        username: Username to normalize and hash.

    Returns:
        SHA-256 digest for use in storage keys.

    Raises:
        None.
    """
    return core_hashing.sha256_hex(normalize_username_key(username))


def username_log_identifier(username: str) -> str:
    """
    Build a non-reversible username identifier for logs.

    Args:
        username: Username to normalize and hash.

    Returns:
        Log-safe username identifier.

    Raises:
        None.
    """
    return f"username_hash={_username_digest(username)}"


def _now_epoch() -> int:
    """Get the current UTC epoch timestamp in seconds."""
    return int(datetime.now(UTC).timestamp())


def _datetime_from_epoch(epoch_seconds: int) -> datetime:
    """Convert an epoch timestamp to a timezone-aware UTC datetime."""
    return datetime.fromtimestamp(epoch_seconds, tz=UTC)


def _log_lockout(display_name: str, duration_label: str, username: str, failed_count: int) -> None:
    """
    Log a progressive lockout event.

    Args:
        display_name: Human-readable store name.
        duration_label: Human-readable lockout duration.
        username: Normalized username being locked out.
        failed_count: Failed attempt count that caused the lockout.

    Returns:
        None.

    Raises:
        None.
    """
    core_logger.print_to_log(
        f"{display_name} lockout ({duration_label}) applied to user "
        f"{username_log_identifier(username)} after {failed_count} "
        "failed attempts",
        "warning",
        context={
            "username_hash": _username_digest(username),
            "failed_attempts": failed_count,
        },
    )


@runtime_checkable
class FailedLoginStore(Protocol):
    """Contract for failed-login lockout stores. Keys are usernames."""

    def is_locked_out(self, username: str) -> bool: ...

    def get_lockout_time(self, username: str) -> datetime | None: ...

    def record_failed_attempt(self, username: str) -> int: ...

    def reset_attempts(self, username: str) -> None: ...

    def clear_all(self) -> None: ...


@runtime_checkable
class PendingMFAStore(Protocol):
    """Contract for pending-MFA login stores (bookkeeping + MFA lockout)."""

    def add_pending_login(self, username: str, user_id: int) -> None: ...

    def get_pending_login(self, username: str) -> int | None: ...

    def claim_pending_login(self, username: str) -> int | None: ...

    def delete_pending_login(self, username: str) -> None: ...

    def has_pending_login(self, username: str) -> bool: ...

    def clear_for_user(self, user_id: int) -> int: ...

    def cleanup_expired(self) -> int: ...

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
_LOGIN_LOCKOUT_THRESHOLDS: tuple[tuple[int, int, str], ...] = (
    (5, 5 * 60, "5 min"),
    (10, 30 * 60, "30 min"),
    (20, 24 * 60 * 60, "24 hours"),
)
_MFA_LOCKOUT_THRESHOLDS: tuple[tuple[int, int, str], ...] = (
    (5, 5 * 60, "5 min"),
    (10, 30 * 60, "30 min"),
    (15, 2 * 60 * 60, "2 hours"),
)
_STEP_UP_LOCKOUT_THRESHOLDS: tuple[tuple[int, int, str], ...] = (
    (5, 5 * 60, "5 min"),
    (10, 30 * 60, "30 min"),
    (15, 2 * 60 * 60, "2 hours"),
)


class _ProgressiveLockout:
    """
    Progressive-lockout counter delegated to ``StateProvider.record_tiered_failure``.

    Shared by all three security stores; the memory-vs-Redis atomicity lives in
    the provider, so this class only holds the thresholds and key layout.

    Attributes:
        _get_state: Callable returning the active state provider.
        _name: Logical store name used in key prefixes.
        _display_name: Human-readable name used in logs.
        _thresholds: ``(count, seconds, label)`` tuples, ascending.
        _attempts_ttl_seconds: TTL for failed-attempt counters.
        _normalize: Optional key-normaliser applied before hashing.
    """

    def __init__(
        self,
        get_state: "Callable[[], StateProvider]",
        name: str,
        display_name: str,
        thresholds: tuple[tuple[int, int, str], ...],
        attempts_ttl_seconds: int,
        normalize_key: "Callable[[str], str] | None" = None,
    ) -> None:
        self._get_state = get_state
        self._name = name
        self._display_name = display_name
        self._thresholds = thresholds
        self._attempts_ttl_seconds = attempts_ttl_seconds
        self._normalize = normalize_key or (lambda key: key)

    def _digest(self, key: str) -> str:
        return core_hashing.sha256_hex(self._normalize(key))

    def _counter_key(self, key: str) -> str:
        return f"{_AUTH_KEY_PREFIX}:{self._name}:attempts:{self._digest(key)}"

    def _gate_key(self, key: str) -> str:
        return f"{_AUTH_KEY_PREFIX}:{self._name}:lockout:{self._digest(key)}"

    def _duration_label(self, failed_count: int) -> str:
        for threshold, _lockout_seconds, label in reversed(self._thresholds):
            if failed_count >= threshold:
                return label
        return "unknown"

    def is_locked_out(self, key: str) -> bool:
        return self.get_lockout_time(key) is not None

    def get_lockout_time(self, key: str) -> datetime | None:
        gate_key = self._gate_key(key)
        try:
            raw_gate = self._get_state().get(gate_key)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("get lockout time", err)
        if raw_gate is None:
            return None
        try:
            gate_until = int(raw_gate.decode())
        except (TypeError, ValueError):
            self._delete(gate_key, "delete invalid lockout")
            return None
        if gate_until <= _now_epoch():
            self._delete(gate_key, "delete expired lockout")
            return None
        return _datetime_from_epoch(gate_until)

    def record_failed_attempt(self, key: str) -> int:
        tiers = tuple((count, seconds) for count, seconds, _label in self._thresholds)
        try:
            outcome = self._get_state().record_tiered_failure(
                self._counter_key(key),
                self._gate_key(key),
                tiers,
                self._attempts_ttl_seconds,
            )
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("record failed attempt", err)
        if outcome.newly_locked:
            _log_lockout(self._display_name, self._duration_label(outcome.count), self._normalize(key), outcome.count)
        return outcome.count

    def reset_attempts(self, key: str) -> None:
        state = self._get_state()
        try:
            state.delete(self._counter_key(key))
            state.delete(self._gate_key(key))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("reset attempts", err)

    def clear_all(self) -> None:
        try:
            self._get_state().delete_prefix(f"{_AUTH_KEY_PREFIX}:{self._name}:")
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("clear lockout store", err)

    def _delete(self, key: str, operation: str) -> None:
        try:
            self._get_state().delete(key)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(operation, err)


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


class PendingMFALogin:
    """
    Manage pending MFA logins plus per-username MFA failure lockout (5/10/15).

    Attributes:
        PENDING_MFA_TTL_SECONDS: TTL for pending MFA entries.
        _state_override: Explicit provider (tests); ``None`` resolves lazily.
        _lockout: Shared progressive-lockout helper for MFA failures.
    """

    PENDING_MFA_TTL_SECONDS: int = 300

    def __init__(self, state: StateProvider | None = None) -> None:
        self._state_override = state
        self._lockout = _ProgressiveLockout(
            self._get_state,
            name="mfa",
            display_name="MFA",
            thresholds=_MFA_LOCKOUT_THRESHOLDS,
            attempts_ttl_seconds=2 * 60 * 60,
            normalize_key=normalize_username_key,
        )

    def _get_state(self) -> StateProvider:
        return self._state_override if self._state_override is not None else platform_runtime.get_state()

    def _pending_key(self, username: str) -> str:
        return f"{_AUTH_KEY_PREFIX}:mfa:pending:{_username_digest(username)}"

    def add_pending_login(self, username: str, user_id: int) -> None:
        """Add a pending MFA login entry for a user."""
        try:
            self._get_state().set(
                self._pending_key(username),
                str(user_id).encode(),
                ttl_seconds=self.PENDING_MFA_TTL_SECONDS,
            )
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("add pending MFA login", err)

    def get_pending_login(self, username: str) -> int | None:
        """Retrieve the user ID for a pending MFA login, evicting corrupt entries."""
        pending_key = self._pending_key(username)
        try:
            raw_user_id = self._get_state().get(pending_key)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("get pending MFA login", err)
        if raw_user_id is None:
            return None
        try:
            return int(raw_user_id.decode())
        except (TypeError, ValueError):
            try:
                self._get_state().delete(pending_key)
            except StateBackendUnavailableError as err:
                _raise_store_unavailable("delete invalid pending MFA login", err)
            return None

    def claim_pending_login(self, username: str) -> int | None:
        """Atomically retrieve and remove a pending MFA login."""
        try:
            raw_user_id = self._get_state().get_and_delete(self._pending_key(username))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("claim pending MFA login", err)
        if raw_user_id is None:
            return None
        try:
            return int(raw_user_id.decode())
        except (TypeError, ValueError):
            return None

    def delete_pending_login(self, username: str) -> None:
        """Remove the pending MFA login entry for a username."""
        try:
            self._get_state().delete(self._pending_key(username))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("delete pending MFA login", err)

    def clear_for_user(self, user_id: int) -> int:
        """Remove every pending MFA login entry tied to a user ID."""
        target_value = str(user_id).encode()
        removed = 0
        state = self._get_state()
        try:
            for pending_key in list(state.iter_keys(f"{_AUTH_KEY_PREFIX}:mfa:pending:")):
                if state.get(pending_key) == target_value:
                    state.delete(pending_key)
                    removed += 1
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("clear pending MFA logins for user", err)
        return removed

    def has_pending_login(self, username: str) -> bool:
        """Check if a username has a valid pending MFA login."""
        return self.get_pending_login(username) is not None

    def cleanup_expired(self) -> int:
        """Return zero because the backend expires pending entries by TTL."""
        return 0

    def is_locked_out(self, username: str) -> bool:
        """Check if a username is locked out from MFA attempts."""
        return self._lockout.is_locked_out(username)

    def get_lockout_time(self, username: str) -> datetime | None:
        """Get the MFA lockout expiry for a username, if locked out."""
        return self._lockout.get_lockout_time(username)

    def record_failed_attempt(self, username: str) -> int:
        """Record a failed MFA attempt and return the current count."""
        return self._lockout.record_failed_attempt(username)

    def reset_attempts(self, username: str) -> None:
        """Reset the MFA failure counter after a successful verification."""
        self._lockout.reset_attempts(username)

    def clear_all(self) -> None:
        """Clear all pending logins and MFA failure records."""
        try:
            self._get_state().delete_prefix(f"{_AUTH_KEY_PREFIX}:mfa:pending:")
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("clear pending MFA logins", err)
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
pending_mfa_store: PendingMFAStore = PendingMFALogin()
step_up_attempts: StepUpStore = StepUpAttempts()


def get_failed_login_attempts() -> FailedLoginStore:
    """Dependency injection for failed-login attempt storage."""
    return failed_login_attempts


def get_pending_mfa_store() -> PendingMFAStore:
    """Dependency injection for pending MFA storage."""
    return pending_mfa_store


def get_step_up_attempts() -> StepUpStore:
    """Dependency injection for step-up attempt tracking."""
    return step_up_attempts


def cleanup_expired_pending_mfa_logins() -> None:
    """Evict all expired pending MFA login entries (no-op; TTL-managed)."""
    pending_mfa_store.cleanup_expired()


def clear_pending_mfa_for_user(user_id: int) -> int:
    """
    Remove pending MFA login entries for a user across credential changes.

    Called from password-change paths so that an attacker who already submitted
    the now-rotated password and is sitting at the pending-MFA step cannot still
    complete the login. Storage outages are logged and swallowed because the
    password rotation itself must remain successful; pending entries expire
    naturally after their 5-minute TTL.

    Args:
        user_id: User ID whose pending MFA entries should be removed.

    Returns:
        Number of pending MFA entries removed (zero on storage outage).

    Raises:
        None.
    """
    try:
        return pending_mfa_store.clear_for_user(user_id)
    except AuthSecurityStoreUnavailableError as err:
        core_logger.print_to_log(
            "Failed to clear pending MFA entries during password change; entries will expire naturally via TTL",
            "warning",
            exc=err,
        )
        return 0
