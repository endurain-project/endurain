"""Shared-state implementation of progressive authentication lockout."""

import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime
from typing import NoReturn

from jasil.providers import StateBackendUnavailableError, StateProvider

import core.hashing as core_hashing
import core.key_derivation as core_key_derivation
import modules.auth.lockout.contracts as lockout_contracts

_AUTH_KEY_PREFIX = "endurain:auth"


def normalize_username_key(username: str) -> str:
    """Return the form the account lookup uses (trimmed, lower-cased), so a name and its lock key always agree."""
    return username.strip().lower()


def _username_digest(username: str) -> str:
    return core_hashing.sha256_hex(normalize_username_key(username))


def username_log_identifier(username: str) -> str:
    """Return a keyed, non-reversible identifier suitable for security logs.

    The identifier is the HMAC-SHA256 of the normalized username under a key derived from ``SECRET_KEY``, in full
    (64 hex characters, the length of the plain digest it replaces), so a reader of the logs cannot confirm a guessed
    username and two entries about one username still match.

    Args:
        username: The username as submitted.

    Returns:
        ``username_hash=`` followed by the keyed digest.

    Raises:
        ValueError: If ``SECRET_KEY`` is not configured.
    """
    key = core_key_derivation.derive_key(core_key_derivation.USERNAME_LOG)
    if key is None:
        raise ValueError("SECRET_KEY is not configured")
    digest = hmac.new(key.encode(), normalize_username_key(username).encode(), hashlib.sha256).hexdigest()
    return f"username_hash={digest}"


def _raise_store_unavailable(err: StateBackendUnavailableError) -> NoReturn:
    raise lockout_contracts.AuthSecurityStoreUnavailableError("auth security storage is unavailable") from err


class ProgressiveLockout:
    """Track progressive failure tiers using a shared platform state provider."""

    def __init__(
        self,
        state: StateProvider,
        *,
        name: str,
        tiers: tuple[lockout_contracts.LockoutTier, ...],
        attempts_ttl_seconds: int,
        normalize_key: Callable[[str], str] | None = None,
    ) -> None:
        """Bind progressive lockout tracking to the shared platform state provider."""
        self._state = state
        self._name = name
        self._tiers = tiers
        self._attempts_ttl_seconds = attempts_ttl_seconds
        self._normalize = normalize_key or (lambda key: key)

    def _digest(self, key: str) -> str:
        return core_hashing.sha256_hex(self._normalize(key))

    def _counter_key(self, key: str) -> str:
        return f"{_AUTH_KEY_PREFIX}:{self._name}:attempts:{self._digest(key)}"

    def _gate_key(self, key: str) -> str:
        return f"{_AUTH_KEY_PREFIX}:{self._name}:lockout:{self._digest(key)}"

    def _delete(self, key: str) -> None:
        try:
            self._state.delete(key)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)

    def is_locked_out(self, key: str) -> bool:
        """Return whether the supplied key is locked out."""
        return self.get_lockout_time(key) is not None

    def get_lockout_time(self, key: str) -> datetime | None:
        """Return the active lockout expiry, if one exists."""
        gate_key = self._gate_key(key)
        try:
            raw_gate = self._state.get(gate_key)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        if raw_gate is None:
            return None
        try:
            gate_until = int(raw_gate.decode())
        except (TypeError, ValueError):
            self._delete(gate_key)
            return None
        if gate_until <= int(datetime.now(UTC).timestamp()):
            self._delete(gate_key)
            return None
        return datetime.fromtimestamp(gate_until, tz=UTC)

    def record_failed_attempt(self, key: str) -> int:
        """Record a failed attempt and return the updated count."""
        return self.record_failure(key).count

    def record_failure(self, key: str) -> lockout_contracts.FailureOutcome:
        """Record a failed attempt and return the updated count with whether it closed the gate."""
        tiers = tuple((count, seconds) for count, seconds, _label in self._tiers)
        try:
            outcome = self._state.record_tiered_failure(
                self._counter_key(key), self._gate_key(key), tiers, self._attempts_ttl_seconds
            )
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        return lockout_contracts.FailureOutcome(outcome.count, outcome.newly_locked)

    def reset_attempts(self, key: str) -> None:
        """Clear the failed-attempt count for the supplied key."""
        try:
            self._state.delete(self._counter_key(key))
            self._state.delete(self._gate_key(key))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        try:
            self._state.delete_prefix(f"{_AUTH_KEY_PREFIX}:{self._name}:")
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
