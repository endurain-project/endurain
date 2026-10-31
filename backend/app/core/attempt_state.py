"""Shared-state plumbing for attempts that run off the request and that a browser polls.

A link attempt, a queued sync or an import may finish on another replica than the one that
accepted it, and is read back by polling. Each keeps a claim, which stops a second attempt for the
same subject, and a state, which the poll reads. Both live in the platform ``StateProvider``
(in-process under ``local``, Redis under ``distributed``), so nothing about them is process-local.
"""

from enum import StrEnum
from typing import NoReturn

from jasil.providers import StateBackendUnavailableError, StateProvider
from pydantic import BaseModel

import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)


class StateUnavailableError(core_exceptions.ServiceUnavailableError):
    """Raised when the attempt state storage backend cannot be reached."""


def raise_unavailable(operation: str, err: StateBackendUnavailableError) -> NoReturn:
    """Log a storage outage and re-raise it as a state error.

    Args:
        operation: Storage operation that failed.
        err: The provider outage error.

    Raises:
        StateUnavailableError: Always raised.
    """
    logger.error("Attempt state storage failed", exc_info=err, extra=core_logger.context(operation=operation))
    raise StateUnavailableError("State storage is unavailable") from err


def key(namespace: str, name: str, subject: str) -> str:
    """Build a storage key.

    Args:
        namespace: The feature that owns the entry, e.g. ``garmin``.
        name: What is stored, e.g. ``mfa:code``.
        subject: Who or what it belongs to, e.g. a user id.

    Returns:
        The storage key.
    """
    return f"endurain:{namespace}:{name}:{subject}"


class AttemptStateStore:
    """A claim plus a polled state for one kind of attempt.

    Attributes:
        _state: The platform state provider.
        _namespace: The feature that owns the entries, in the storage keys.
        _name: Names this kind of attempt in the storage keys.
        _ttl_seconds: Lifetime of the claim and the state. It must exceed the attempt's
            longest legitimate run, and each recorded progress renews the claim, so only a
            dead replica's claim runs out, which frees a retry.
    """

    def __init__(self, state: StateProvider, namespace: str, name: str, ttl_seconds: int) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider.
            namespace: The feature that owns the entries, in the storage keys.
            name: Names this kind of attempt in the storage keys.
            ttl_seconds: Lifetime of the claim and the state.
        """
        self._state = state
        self._namespace = namespace
        self._name = name
        self._ttl_seconds = ttl_seconds

    def _state_key(self, subject: str) -> str:
        return key(self._namespace, f"{self._name}:state", subject)

    def _claim_key(self, subject: str) -> str:
        return key(self._namespace, f"{self._name}:claim", subject)

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
            StateUnavailableError: When storage is unavailable.
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
            raise_unavailable(f"begin {self._namespace}:{self._name}", err)
        return True

    def release(self, subject: str) -> None:
        """Drop a claim, leaving it to expire when storage cannot be reached.

        Args:
            subject: What the attempt was for.
        """
        try:
            self._state.delete(self._claim_key(subject))
        except StateBackendUnavailableError as err:
            logger.warning(
                "Failed to release an attempt claim; it will expire",
                exc_info=err,
                extra=core_logger.context(namespace=self._namespace, name=self._name),
            )

    def discard(self, subject: str) -> None:
        """Drop an attempt's claim and state, for one that was refused before it started.

        Unlike :meth:`release`, nothing is left for the status route to report. Entries storage
        cannot reach are left to expire.

        Args:
            subject: What the attempt was for.
        """
        try:
            self._state.delete(self._claim_key(subject))
            self._state.delete(self._state_key(subject))
        except StateBackendUnavailableError as err:
            logger.warning(
                "Failed to discard an attempt; it will expire",
                exc_info=err,
                extra=core_logger.context(namespace=self._namespace, name=self._name),
            )

    def record(self, subject: str, state: BaseModel, *, finished: bool, strict: bool = False) -> None:
        """Record an attempt's progress or outcome.

        A finished attempt releases its claim; any other progress renews it. A failure to
        record is logged, not raised: the attempt itself must still finish, and the entries
        expire on their own. A state that a later decision depends on is recorded ``strict``,
        so losing it raises instead.

        Args:
            subject: What the attempt is for.
            state: The new state.
            finished: Whether the attempt is over.
            strict: Raise when the state cannot be recorded.

        Raises:
            StateUnavailableError: When ``strict`` and storage is unavailable.
        """
        try:
            self._write(subject, state)
            if finished:
                self._state.delete(self._claim_key(subject))
            else:
                self._state.set(self._claim_key(subject), b"1", ttl_seconds=self._ttl_seconds)
        except StateBackendUnavailableError as err:
            if strict:
                raise_unavailable(f"record {self._namespace}:{self._name}", err)
            logger.warning(
                "Failed to record an attempt state",
                exc_info=err,
                extra=core_logger.context(namespace=self._namespace, name=self._name),
            )

    def read(self, subject: str) -> bytes | None:
        """Read an attempt's recorded state.

        Args:
            subject: What the attempt is for.

        Returns:
            The stored state, or None when none is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        try:
            return self._state.get(self._state_key(subject))
        except StateBackendUnavailableError as err:
            raise_unavailable(f"read {self._namespace}:{self._name}", err)


class SyncStatus(StrEnum):
    """Where a queued provider sync is."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncState(BaseModel):
    """The recorded state of one queued sync.

    Attributes:
        status: Where the sync is.
    """

    status: SyncStatus


#: Lifetime of a queued sync's claim and state: longer than any sync takes, shorter than a stuck claim should
#: block the user.
SYNC_TTL_SECONDS = 30 * 60

_PENDING = (SyncStatus.QUEUED, SyncStatus.RUNNING)
_FINISHED = (SyncStatus.COMPLETED, SyncStatus.FAILED)


class SyncStateStore:
    """The claim and polled state of a feature's queued syncs, one per user and kind.

    A sync is accepted with 202 and runs on a worker, possibly on another replica. The state is
    what the status route reads back, and its claim keeps a user from queueing the same kind of
    sync twice. A feature subclasses this to fix its namespace and lifetime.

    Attributes:
        _attempts: The claim and state storage for the feature's syncs.
    """

    def __init__(self, state: StateProvider, namespace: str, ttl_seconds: int = SYNC_TTL_SECONDS) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider.
            namespace: The feature that owns the syncs, in the storage keys.
            ttl_seconds: How long a sync's claim and state last.
        """
        self._attempts = AttemptStateStore(state, namespace, "sync", ttl_seconds)

    @staticmethod
    def _subject(user_id: int, kind: StrEnum) -> str:
        return f"{user_id}:{kind.value}"

    def begin(self, user_id: int, kind: StrEnum) -> bool:
        """Record a sync as queued unless one of this kind is still pending.

        Args:
            user_id: The user to sync.
            kind: What the sync does.

        Returns:
            True when the sync was recorded as queued, False when one is already pending.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        return self._attempts.begin(self._subject(user_id, kind), SyncState(status=SyncStatus.QUEUED))

    def set_status(self, user_id: int, kind: StrEnum, status: SyncStatus) -> None:
        """Record a sync's progress or outcome; a finished sync frees the claim.

        Args:
            user_id: The user being synced.
            kind: What the sync does.
            status: The new status.
        """
        self._attempts.record(self._subject(user_id, kind), SyncState(status=status), finished=status in _FINISHED)

    def discard(self, user_id: int, kind: StrEnum) -> None:
        """Drop a sync's claim and state, for one that was called off.

        Unlike a finished sync, nothing is left for the status route to report.

        Args:
            user_id: The user being synced.
            kind: What the sync does.
        """
        self._attempts.discard(self._subject(user_id, kind))

    def get(self, user_id: int, kind: StrEnum) -> SyncState | None:
        """Read a sync's state.

        Args:
            user_id: The user being synced.
            kind: What the sync does.

        Returns:
            The state, or None when none is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        value = self._attempts.read(self._subject(user_id, kind))
        return SyncState.model_validate_json(value) if value is not None else None

    def close_pending(self, user_id: int, kind: StrEnum) -> bool:
        """Fail a sync that is still pending, so the user can queue another.

        For a sync the runner gave up on, however its last attempt ended. A sync that already
        finished, or whose state has expired, is left as it is.

        Args:
            user_id: The user being synced.
            kind: What the sync does.

        Returns:
            True when a pending sync was closed.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        state = self.get(user_id, kind)
        if state is None or state.status not in _PENDING:
            return False
        self.set_status(user_id, kind, SyncStatus.FAILED)
        return True
