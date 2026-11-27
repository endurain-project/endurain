"""Shared state of a queued gear deletion.

A deletion is accepted with 202 and runs on a worker, possibly on another replica. The state is what
``GET /jobs/{job_id}`` reads back, and its claim keeps one gear from being queued for deletion twice. It lives in
the platform ``StateProvider`` (see :mod:`core.attempt_state`).

Interface::

    begin(gear_id, owner_id, conflict=)  - queue a deletion, returning its job; raises while one is pending
    set_status(gear_id, status)          - record progress or the outcome
    get(gear_id)                         - read the current state, or None once expired
    read_job(job)                        - read the deletion a job reference names
    close_pending(gear_id)               - fail a deletion that is still pending
"""

import uuid

from jasil.providers import StateProvider
from pydantic import BaseModel, model_validator

import core.attempt_state as core_attempt_state
import core.job_status as core_job_status
import modules.gears.gear.constants as gears_constants
import modules.websocket.integration_service as websocket_integration

_PENDING = (core_job_status.JobState.QUEUED, core_job_status.JobState.RUNNING)


class GearDeletionState(BaseModel):
    """The recorded state of one gear deletion.

    Attributes:
        status: Where the deletion is.
    """

    status: core_job_status.JobState

    @model_validator(mode="before")
    @classmethod
    def _read_stored_state(cls, data: object) -> object:
        """Read a state stored before the shared job vocabulary as the current one."""
        return core_job_status.upgrade_stored_state(data)


class GearDeletionStateStore:
    """Gear deletion state backed by the platform ``StateProvider``.

    Attributes:
        _attempts: The claim and state storage for deletions.
    """

    def __init__(self, state: StateProvider, ttl_seconds: int = gears_constants.DELETION_STATE_TTL_SECONDS) -> None:
        """Initialize the deletion state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long a deletion's claim and state last.
        """
        self._attempts = core_attempt_state.AttemptStateStore(
            state, "gears", "deletion", ttl_seconds, announce=websocket_integration.announce_job
        )

    def begin(self, gear_id: uuid.UUID, owner_id: uuid.UUID, *, conflict: str) -> core_job_status.JobRef:
        """Record a deletion as queued unless one is still pending for the gear.

        Args:
            gear_id: The gear to delete.
            owner_id: The user who asked for the deletion and may read it.
            conflict: The detail of the error for a deletion already pending.

        Returns:
            The new job's reference.

        Raises:
            JobAlreadyRunningError: When a deletion of the gear is already pending.
            StateUnavailableError: When storage is unavailable.
        """
        return self._attempts.begin(
            str(gear_id),
            GearDeletionState(status=core_job_status.JobState.QUEUED),
            kind=gears_constants.DELETION_JOB,
            owner_id=owner_id,
            conflict=conflict,
        )

    def set_status(self, gear_id: uuid.UUID, job_id: uuid.UUID, status: core_job_status.JobState) -> None:
        """Record a deletion's progress or outcome; a finished deletion frees the claim.

        A deletion that a newer one has superseded records nothing.

        Args:
            gear_id: The gear being deleted.
            job_id: The job the caller is running.
            status: The new status.
        """
        self._attempts.record(
            str(gear_id), job_id, GearDeletionState(status=status), finished=status in core_job_status.TERMINAL_STATES
        )

    def get(self, gear_id: uuid.UUID, *, job_id: uuid.UUID | None = None) -> GearDeletionState | None:
        """Read a gear's deletion state.

        Args:
            gear_id: The gear being deleted.
            job_id: When given, read the state only while it belongs to this job.

        Returns:
            The state, or None when none is recorded, it has expired or, with ``job_id``, it belongs to another
            job.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        value = self._attempts.read(str(gear_id), job_id=job_id)
        return GearDeletionState.model_validate_json(value) if value is not None else None

    def read_job(self, job: core_job_status.JobRef) -> tuple[core_job_status.JobRef, GearDeletionState] | None:
        """Read the deletion a job reference names.

        Args:
            job: The job's reference, from :class:`core.attempt_state.JobIndex`.

        Returns:
            The job's current reference and state, or None when its record is gone or belongs to a later deletion.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        stored = self._attempts.read_job(job)
        return (stored.job, GearDeletionState.model_validate_json(stored.state_json())) if stored is not None else None

    def close_pending(self, gear_id: uuid.UUID, job_id: uuid.UUID) -> bool:
        """Fail a deletion that is still pending, so the user can queue it again.

        For a deletion the runner gave up on, however its last attempt ended. One that already finished, or
        whose state has expired, or that a newer deletion superseded, is left as it is.

        Args:
            gear_id: The gear being deleted.
            job_id: The job the runner gave up on.

        Returns:
            True when a pending deletion was closed.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        state = self.get(gear_id, job_id=job_id)
        if state is None or state.status not in _PENDING:
            return False
        self.set_status(gear_id, job_id, core_job_status.JobState.FAILED)
        return True
