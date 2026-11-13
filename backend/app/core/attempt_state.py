"""Shared-state plumbing for attempts that run off the request and that a browser polls.

A link attempt, a queued sync or an import may finish on another replica than the one that
accepted it, and is read back by polling. Each keeps a claim, which stops a second attempt for the
same subject, and a state, which the poll reads. Each attempt is a job with its own id, which
:class:`JobIndex` resolves for ``GET /jobs/{job_id}``. All of it lives in the platform ``StateProvider``
(in-process under ``local``, Redis under ``distributed``), so nothing about them is process-local.
"""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import NoReturn

from jasil.providers import StateBackendUnavailableError, StateProvider
from pydantic import BaseModel, ValidationError, model_validator

import core.exceptions as core_exceptions
import core.job_status as core_job_status
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


class JobIndex:
    """Finds a job by its id, and lists the jobs a user started.

    Each job has two entries: its reference under its id, and the same reference under its owner, which
    ``GET /jobs`` walks. Both are rewritten whenever the job's state is, with the state's lifetime, so a job is
    indexed exactly as long as its record lasts.

    Attributes:
        _state: The platform state provider.
    """

    def __init__(self, state: StateProvider) -> None:
        """Initialize the index.

        Args:
            state: The platform state provider.
        """
        self._state = state

    @staticmethod
    def _ref_key(job_id: uuid.UUID) -> str:
        return key("jobs", "ref", str(job_id))

    @staticmethod
    def _owner_prefix(owner_id: uuid.UUID) -> str:
        return key("jobs", "owner", f"{owner_id}:")

    def put(self, job: core_job_status.JobRef, ttl_seconds: int) -> None:
        """Index a job, or renew its entries with the job's latest reference.

        Args:
            job: The job's reference.
            ttl_seconds: How long the entries last; the lifetime of the job's state.

        Raises:
            StateBackendUnavailableError: When storage is unavailable; the caller decides whether that is fatal.
        """
        value = job.model_dump_json().encode()
        self._state.set(self._ref_key(job.id), value, ttl_seconds=ttl_seconds)
        self._state.set(self._owner_prefix(job.owner_id) + str(job.id), value, ttl_seconds=ttl_seconds)

    def remove(self, job: core_job_status.JobRef) -> None:
        """Drop a job's entries.

        Args:
            job: The job's reference.

        Raises:
            StateBackendUnavailableError: When storage is unavailable.
        """
        self._state.delete(self._ref_key(job.id))
        self._state.delete(self._owner_prefix(job.owner_id) + str(job.id))

    def get(self, job_id: uuid.UUID) -> core_job_status.JobRef | None:
        """Read the reference a job id names.

        Args:
            job_id: The job's identifier.

        Returns:
            The reference, or None when no such job is indexed or its record has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        try:
            value = self._state.get(self._ref_key(job_id))
        except StateBackendUnavailableError as err:
            raise_unavailable("read job reference", err)
        return core_job_status.JobRef.model_validate_json(value) if value is not None else None

    def list_owned(self, owner_id: uuid.UUID) -> list[core_job_status.JobRef]:
        """List the references of the jobs a user started whose records still last.

        Args:
            owner_id: The user who started the jobs.

        Returns:
            The references, in no particular order.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        try:
            values = [self._state.get(entry) for entry in self._state.iter_keys(self._owner_prefix(owner_id))]
        except StateBackendUnavailableError as err:
            raise_unavailable("list owned jobs", err)
        # An entry can expire between the walk and its read.
        return [core_job_status.JobRef.model_validate_json(value) for value in values if value is not None]


class StoredJob(BaseModel):
    """A job's reference and the state its feature recorded, as one stored value.

    Attributes:
        job: The job's reference.
        state: The feature's own state model, as JSON.
    """

    job: core_job_status.JobRef
    state: dict[str, object]

    def state_json(self) -> bytes:
        """Return the feature's state as the JSON its model validates.

        Returns:
            The state, encoded.
        """
        return json.dumps(self.state).encode()


class AttemptStateStore:
    """A claim plus a polled state for one kind of attempt, each attempt a job with its own id.

    The claim holds the running job's id, so a refused second start can name the job to poll. The state holds
    the job's reference beside the feature's own fields, and :class:`JobIndex` finds it by id.

    Attributes:
        _state: The platform state provider.
        _namespace: The feature that owns the entries, in the storage keys.
        _name: Names this kind of attempt in the storage keys.
        _ttl_seconds: Lifetime of the claim, the state and the index entries. It must exceed the attempt's
            longest legitimate run, and each recorded progress renews the claim, so only a dead replica's claim
            runs out, which frees a retry.
        _index: The index the jobs are found by.
        _announce: Tells the owner's client that a job reached a final status, when the feature wires it.
    """

    def __init__(
        self,
        state: StateProvider,
        namespace: str,
        name: str,
        ttl_seconds: int,
        *,
        announce: Callable[[core_job_status.JobRef], None] | None = None,
    ) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider.
            namespace: The feature that owns the entries, in the storage keys.
            name: Names this kind of attempt in the storage keys.
            ttl_seconds: Lifetime of the claim and the state.
            announce: Called with the job's reference when it reaches a final status, to tell the owner's
                client; the store holds no transport of its own.
        """
        self._state = state
        self._namespace = namespace
        self._name = name
        self._ttl_seconds = ttl_seconds
        self._index = JobIndex(state)
        self._announce = announce

    def _state_key(self, subject: str) -> str:
        return key(self._namespace, f"{self._name}:state", subject)

    def _claim_key(self, subject: str) -> str:
        return key(self._namespace, f"{self._name}:claim", subject)

    def _write(self, stored: StoredJob) -> None:
        self._state.set(
            self._state_key(stored.job.subject), stored.model_dump_json().encode(), ttl_seconds=self._ttl_seconds
        )
        self._index.put(stored.job, self._ttl_seconds)

    def _read_stored(self, subject: str) -> StoredJob | None:
        value = self._state.get(self._state_key(subject))
        if value is None:
            return None
        try:
            return StoredJob.model_validate_json(value)
        except ValidationError:
            # A state the previous release wrote carries no job; it reads as none, and its claim still expires.
            return None

    def _running_job_id(self, subject: str) -> uuid.UUID | None:
        value = self._state.get(self._claim_key(subject))
        if value is None:
            return None
        job_id = uuid.UUID(value.decode())
        return job_id if self._index.get(job_id) is not None else None

    def begin(
        self, subject: str, initial: BaseModel, *, kind: str, owner_id: uuid.UUID, conflict: str
    ) -> core_job_status.JobRef:
        """Start an attempt as a new job unless one is still running.

        The claim is one atomic ``set_if_absent``, so two requests racing across replicas cannot both start. A
        finished attempt releases it.

        Args:
            subject: What the attempt is for.
            initial: The state to record once the claim is held.
            kind: What the job does, for its reference.
            owner_id: The user starting the job, who may read it.
            conflict: The detail of the error for an attempt already running.

        Returns:
            The new job's reference.

        Raises:
            JobAlreadyRunningError: When another attempt is in progress; it names that job when it can.
            StateUnavailableError: When storage is unavailable.
        """
        job = core_job_status.JobRef(
            id=uuid.uuid4(), kind=kind, owner_id=owner_id, subject=subject, created_at=datetime.now(UTC)
        )
        try:
            if not self._state.set_if_absent(self._claim_key(subject), str(job.id).encode(), self._ttl_seconds):
                raise core_exceptions.JobAlreadyRunningError(conflict, job_id=self._running_job_id(subject))
            try:
                self._write(StoredJob(job=job, state=initial.model_dump(mode="json")))
            except StateBackendUnavailableError:
                self.release(subject)
                raise
        except StateBackendUnavailableError as err:
            raise_unavailable(f"begin {self._namespace}:{self._name}", err)
        return job

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
        """Drop an attempt's claim, state and job, for one that was refused before it started.

        Unlike :meth:`release`, nothing is left to report. Entries storage cannot reach are left to expire.

        Args:
            subject: What the attempt was for.
        """
        try:
            stored = self._read_stored(subject)
            self._state.delete(self._claim_key(subject))
            self._state.delete(self._state_key(subject))
            if stored is not None:
                self._index.remove(stored.job)
        except StateBackendUnavailableError as err:
            logger.warning(
                "Failed to discard an attempt; it will expire",
                exc_info=err,
                extra=core_logger.context(namespace=self._namespace, name=self._name),
            )

    def record(self, subject: str, state: BaseModel, *, finished: bool, strict: bool = False) -> None:
        """Record an attempt's progress or outcome.

        A finished attempt releases its claim, stamps its job's ``finished_at`` and is announced; any other
        progress renews the claim. A failure to record is logged, not raised: the attempt itself must still
        finish, and the entries expire on their own. A state that a later decision depends on is recorded
        ``strict``, so losing it raises instead. An attempt whose job has expired, or that the previous release
        began, has no job to record against: only its claim is kept or released.

        Args:
            subject: What the attempt is for.
            state: The new state.
            finished: Whether the attempt is over.
            strict: Raise when the state cannot be recorded.

        Raises:
            StateUnavailableError: When ``strict`` and storage is unavailable.
        """
        job: core_job_status.JobRef | None = None
        try:
            stored = self._read_stored(subject)
            if stored is None:
                logger.warning(
                    "An attempt has no job to record its state against",
                    extra=core_logger.context(namespace=self._namespace, name=self._name),
                )
            else:
                job = stored.job
                if finished and job.finished_at is None:
                    job = job.model_copy(update={"finished_at": datetime.now(UTC)})
                self._write(StoredJob(job=job, state=state.model_dump(mode="json")))
            if finished:
                self._state.delete(self._claim_key(subject))
            elif job is not None:
                self._state.set(self._claim_key(subject), str(job.id).encode(), ttl_seconds=self._ttl_seconds)
        except StateBackendUnavailableError as err:
            if strict:
                raise_unavailable(f"record {self._namespace}:{self._name}", err)
            logger.warning(
                "Failed to record an attempt state",
                exc_info=err,
                extra=core_logger.context(namespace=self._namespace, name=self._name),
            )
            return
        if finished and job is not None and self._announce is not None:
            self._announce(job)

    def read_stored(self, subject: str) -> StoredJob | None:
        """Read an attempt's job and recorded state.

        Args:
            subject: What the attempt is for.

        Returns:
            The job and its state, or None when none is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        try:
            return self._read_stored(subject)
        except StateBackendUnavailableError as err:
            raise_unavailable(f"read {self._namespace}:{self._name}", err)

    def read(self, subject: str) -> bytes | None:
        """Read an attempt's recorded state.

        Args:
            subject: What the attempt is for.

        Returns:
            The feature's state as JSON, or None when none is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        stored = self.read_stored(subject)
        return stored.state_json() if stored is not None else None

    def read_job(self, job: core_job_status.JobRef) -> StoredJob | None:
        """Read the record of the job a reference names.

        The record of a subject is replaced when its next job starts, so a reference to an earlier job reads
        as gone.

        Args:
            job: The job's reference, from :class:`JobIndex`.

        Returns:
            The job's current reference and state, or None when its record is gone or belongs to a later job.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        stored = self.read_stored(job.subject)
        return stored if stored is not None and stored.job.id == job.id else None


class SyncState(BaseModel):
    """The recorded state of one queued sync.

    Attributes:
        status: Where the sync is.
    """

    status: core_job_status.JobState

    @model_validator(mode="before")
    @classmethod
    def _read_stored_state(cls, data: object) -> object:
        """Read a state stored before the shared job vocabulary as the current one."""
        return core_job_status.upgrade_stored_state(data)


#: Lifetime of a queued sync's claim and state: longer than any sync takes, shorter than a stuck claim should
#: block the user.
SYNC_TTL_SECONDS = 30 * 60

_PENDING = (core_job_status.JobState.QUEUED, core_job_status.JobState.RUNNING)
_FINISHED = tuple(core_job_status.TERMINAL_STATES)


class SyncStateStore:
    """The claim and polled state of a feature's queued syncs, one running per user and kind.

    A sync is accepted with 202 and runs on a worker, possibly on another replica. Each sync is a job with its
    own id, read at ``GET /jobs/{job_id}``, and its claim keeps a user from queueing the same kind of sync twice.
    A feature subclasses this to fix its namespace, lifetime and job kinds.

    Attributes:
        _attempts: The claim and state storage for the feature's syncs.
        _job_kind: The job kind of each sync kind.
    """

    def __init__(
        self,
        state: StateProvider,
        namespace: str,
        ttl_seconds: int = SYNC_TTL_SECONDS,
        *,
        job_kind: Callable[[StrEnum], str],
        announce: Callable[[core_job_status.JobRef], None] | None = None,
    ) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider.
            namespace: The feature that owns the syncs, in the storage keys.
            ttl_seconds: How long a sync's claim and state last.
            job_kind: Returns the job kind of a sync kind, e.g. ``garmin_sync_gear`` for ``gear``.
            announce: Called with the job's reference when a sync reaches a final status, to tell the owner's
                client; the store holds no transport of its own.
        """
        self._attempts = AttemptStateStore(state, namespace, "sync", ttl_seconds, announce=announce)
        self._job_kind = job_kind

    @staticmethod
    def _subject(user_id: uuid.UUID, kind: StrEnum) -> str:
        return f"{user_id}:{kind.value}"

    def begin(
        self, user_id: uuid.UUID, kind: StrEnum, *, conflict: str, owner_id: uuid.UUID | None = None
    ) -> core_job_status.JobRef:
        """Record a sync as a queued job unless one of this kind is still pending.

        Args:
            user_id: The user to sync.
            kind: What the sync does.
            conflict: The detail of the error for a sync already pending.
            owner_id: The user who asked for the sync and may read it, when not ``user_id`` itself.

        Returns:
            The new job's reference.

        Raises:
            JobAlreadyRunningError: When a sync of this kind is already pending.
            StateUnavailableError: When storage is unavailable.
        """
        return self._attempts.begin(
            self._subject(user_id, kind),
            SyncState(status=core_job_status.JobState.QUEUED),
            kind=self._job_kind(kind),
            owner_id=user_id if owner_id is None else owner_id,
            conflict=conflict,
        )

    def set_status(self, user_id: uuid.UUID, kind: StrEnum, status: core_job_status.JobState) -> None:
        """Record a sync's progress or outcome; a finished sync frees the claim.

        Args:
            user_id: The user being synced.
            kind: What the sync does.
            status: The new status.
        """
        self._attempts.record(self._subject(user_id, kind), SyncState(status=status), finished=status in _FINISHED)

    def discard(self, user_id: uuid.UUID, kind: StrEnum) -> None:
        """Drop a sync's claim, state and job, for one that was called off.

        Unlike a finished sync, nothing is left to report.

        Args:
            user_id: The user being synced.
            kind: What the sync does.
        """
        self._attempts.discard(self._subject(user_id, kind))

    def get(self, user_id: uuid.UUID, kind: StrEnum) -> SyncState | None:
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

    def read_job(self, job: core_job_status.JobRef) -> tuple[core_job_status.JobRef, SyncState] | None:
        """Read the sync a job reference names.

        Args:
            job: The job's reference, from :class:`JobIndex`.

        Returns:
            The job's current reference and state, or None when its record is gone or belongs to a later sync.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        stored = self._attempts.read_job(job)
        return (stored.job, SyncState.model_validate_json(stored.state_json())) if stored is not None else None

    def close_pending(self, user_id: uuid.UUID, kind: StrEnum) -> bool:
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
        self.set_status(user_id, kind, core_job_status.JobState.FAILED)
        return True
