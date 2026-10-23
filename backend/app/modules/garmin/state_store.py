"""Shared-state plumbing for Garmin Connect attempts that a browser polls.

A link attempt and a queued sync both run off the request, may finish on another replica than
the one that accepted them, and are read back by polling. Both keep a claim, which stops a
second attempt for the same subject, and a state, which the poll reads. The claim and the state
live in the platform ``StateProvider`` (in-process under ``local``, Redis under ``distributed``),
so nothing about them is process-local.
"""

from typing import NoReturn

from jasil.providers import StateBackendUnavailableError, StateProvider
from pydantic import BaseModel

import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

_KEY_PREFIX = "endurain:garmin"


class GarminStateUnavailableError(core_exceptions.ServiceUnavailableError):
    """Raised when the Garmin Connect state storage backend cannot be reached."""


def raise_unavailable(operation: str, err: StateBackendUnavailableError) -> NoReturn:
    """Log a storage outage and re-raise it as a Garmin state error.

    Args:
        operation: Storage operation that failed.
        err: The provider outage error.

    Raises:
        GarminStateUnavailableError: Always raised.
    """
    logger.error(
        "Garmin state storage failed",
        exc_info=err,
        extra=core_logger.context(operation=operation),
    )
    raise GarminStateUnavailableError("Garmin state storage is unavailable") from err


def key(name: str, subject: str) -> str:
    """Build a storage key.

    Args:
        name: What is stored, e.g. ``mfa:code``.
        subject: Who or what it belongs to, e.g. a user id.

    Returns:
        The storage key.
    """
    return f"{_KEY_PREFIX}:{name}:{subject}"


class AttemptStateStore:
    """A claim plus a polled state for one kind of Garmin Connect attempt.

    Attributes:
        _state: The platform state provider.
        _name: Names this kind of attempt in the storage keys.
        _ttl_seconds: Lifetime of the claim and the state. It must exceed the attempt's
            longest legitimate run, and each recorded progress renews the claim, so only a
            dead replica's claim runs out, which frees a retry.
    """

    def __init__(self, state: StateProvider, name: str, ttl_seconds: int) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider.
            name: Names this kind of attempt in the storage keys.
            ttl_seconds: Lifetime of the claim and the state.
        """
        self._state = state
        self._name = name
        self._ttl_seconds = ttl_seconds

    def _state_key(self, subject: str) -> str:
        return key(f"{self._name}:state", subject)

    def _claim_key(self, subject: str) -> str:
        return key(f"{self._name}:claim", subject)

    def _write(self, subject: str, state: BaseModel) -> None:
        self._state.set(self._state_key(subject), state.model_dump_json().encode(), ttl_seconds=self._ttl_seconds)

    def begin(self, subject: str, initial: BaseModel) -> bool:
        """Start an attempt unless one is still running.

        The claim is one atomic ``set_if_absent``, so two requests racing across replicas
        cannot both start. A finished attempt releases it.

        Args:
            subject: What the attempt is for.
            initial: The state to record once the claim is held.

        Returns:
            True when the attempt was recorded, False when another is in progress.

        Raises:
            GarminStateUnavailableError: When storage is unavailable.
        """
        try:
            if not self._state.set_if_absent(self._claim_key(subject), b"1", self._ttl_seconds):
                return False
            try:
                self._write(subject, initial)
            except StateBackendUnavailableError:
                self.release(subject)
                raise
        except StateBackendUnavailableError as err:
            raise_unavailable(f"begin {self._name}", err)
        return True

    def release(self, subject: str) -> None:
        """Drop a claim, leaving it to expire when storage cannot be reached.

        Args:
            subject: What the attempt was for.
        """
        try:
            self._state.delete(self._claim_key(subject))
        except StateBackendUnavailableError as err:
            logger.warning("Failed to release a Garmin claim; it will expire", exc_info=err)

    def record(self, subject: str, state: BaseModel, *, finished: bool) -> None:
        """Record an attempt's progress or outcome.

        A finished attempt releases its claim; any other progress renews it. A failure to
        record is logged, not raised: the attempt itself must still finish, and the entries
        expire on their own.

        Args:
            subject: What the attempt is for.
            state: The new state.
            finished: Whether the attempt is over.
        """
        try:
            self._write(subject, state)
            if finished:
                self._state.delete(self._claim_key(subject))
            else:
                self._state.set(self._claim_key(subject), b"1", ttl_seconds=self._ttl_seconds)
        except StateBackendUnavailableError as err:
            logger.warning("Failed to record a Garmin attempt state", exc_info=err)

    def read(self, subject: str) -> bytes | None:
        """Read an attempt's recorded state.

        Args:
            subject: What the attempt is for.

        Returns:
            The stored state, or None when none is recorded or it has expired.

        Raises:
            GarminStateUnavailableError: When storage is unavailable.
        """
        try:
            return self._state.get(self._state_key(subject))
        except StateBackendUnavailableError as err:
            raise_unavailable(f"read {self._name}", err)
