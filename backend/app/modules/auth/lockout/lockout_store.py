"""Shared-state implementation of progressive authentication lockout."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import NoReturn
from urllib.parse import unquote

from jasil.providers import StateBackendUnavailableError, StateProvider

import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.lockout.contracts as lockout_contracts

logger = core_logger.get_logger(__name__)
_AUTH_KEY_PREFIX = "endurain:auth"


def normalize_username_key(username: str) -> str:
    """Normalize a username before using it as a lockout key."""
    return unquote(username).replace("+", " ").strip().casefold()


def _username_digest(username: str) -> str:
    return core_hashing.sha256_hex(normalize_username_key(username))


def username_log_identifier(username: str) -> str:
    """Return a non-reversible identifier suitable for security logs."""
    return f"username_hash={_username_digest(username)}"


def _raise_store_unavailable(operation: str, err: StateBackendUnavailableError) -> NoReturn:
    logger.error("Authentication lockout storage failed", exc_info=err, extra=core_logger.context(operation=operation))
    raise lockout_contracts.AuthSecurityStoreUnavailableError("auth security storage is unavailable") from err


class ProgressiveLockout:
    """Track progressive failure tiers using a shared platform state provider."""

    def __init__(
        self,
        state: StateProvider,
        *,
        name: str,
        display_name: str,
        tiers: tuple[lockout_contracts.LockoutTier, ...],
        attempts_ttl_seconds: int,
        normalize_key: Callable[[str], str] | None = None,
    ) -> None:
        """Bind progressive lockout tracking to the shared platform state provider."""
        self._state = state
        self._name = name
        self._display_name = display_name
        self._tiers = tiers
        self._attempts_ttl_seconds = attempts_ttl_seconds
        self._normalize = normalize_key or (lambda key: key)

    def _digest(self, key: str) -> str:
        return core_hashing.sha256_hex(self._normalize(key))

    def _counter_key(self, key: str) -> str:
        return f"{_AUTH_KEY_PREFIX}:{self._name}:attempts:{self._digest(key)}"

    def _gate_key(self, key: str) -> str:
        return f"{_AUTH_KEY_PREFIX}:{self._name}:lockout:{self._digest(key)}"

    def _delete(self, key: str, operation: str) -> None:
        try:
            self._state.delete(key)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(operation, err)

    def is_locked_out(self, key: str) -> bool:
        """Return whether the supplied key is locked out."""
        return self.get_lockout_time(key) is not None

    def get_lockout_time(self, key: str) -> datetime | None:
        """Return the active lockout expiry, if one exists."""
        gate_key = self._gate_key(key)
        try:
            raw_gate = self._state.get(gate_key)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("get lockout time", err)
        if raw_gate is None:
            return None
        try:
            gate_until = int(raw_gate.decode())
        except (TypeError, ValueError):
            self._delete(gate_key, "delete invalid lockout")
            return None
        if gate_until <= int(datetime.now(UTC).timestamp()):
            self._delete(gate_key, "delete expired lockout")
            return None
        return datetime.fromtimestamp(gate_until, tz=UTC)

    def record_failed_attempt(self, key: str) -> int:
        """Record a failed attempt and return the updated count."""
        tiers = tuple((count, seconds) for count, seconds, _label in self._tiers)
        try:
            outcome = self._state.record_tiered_failure(
                self._counter_key(key), self._gate_key(key), tiers, self._attempts_ttl_seconds
            )
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("record failed attempt", err)
        if outcome.newly_locked:
            logger.warning(
                "Progressive authentication lockout applied",
                extra=core_logger.context(
                    store=self._display_name,
                    username_hash=_username_digest(key) if self._normalize is normalize_username_key else None,
                    failed_attempts=outcome.count,
                ),
            )
        return outcome.count

    def reset_attempts(self, key: str) -> None:
        """Clear the failed-attempt count for the supplied key."""
        try:
            self._state.delete(self._counter_key(key))
            self._state.delete(self._gate_key(key))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("reset attempts", err)

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        try:
            self._state.delete_prefix(f"{_AUTH_KEY_PREFIX}:{self._name}:")
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("clear lockout store", err)
