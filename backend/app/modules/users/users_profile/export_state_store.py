"""Shared state of a profile export.

An export is accepted with 202 and built on a worker, possibly on another replica. The state is
what ``GET /jobs/{job_id}`` reads back, and its claim keeps a user from queueing two exports at
once. It lives in the platform ``StateProvider`` (see :mod:`core.attempt_state`).

Interface::

    begin(user_id, conflict=)               - queue an export, returning its job; raises while one is pending
    set_status(user_id, status, ...)        - record progress or the outcome
    get(user_id)                            - read the current state, or None once expired
    read_job(job)                           - read the export a job reference names
"""

import uuid
from datetime import UTC, datetime, timedelta

from jasil.providers import StateProvider
from pydantic import BaseModel, model_validator

import core.attempt_state as core_attempt_state
import core.job_status as core_job_status
import modules.users.users_profile.constants as profile_constants
import modules.websocket.integration_service as websocket_integration


class ProfileExportState(BaseModel):
    """The recorded state of one export.

    Attributes:
        status: Where the export is.
        error_code: Why it failed; set only when ``status`` is ``FAILED``.
        size_bytes: Size of the staged archive; set only when ``status`` is ``COMPLETED``.
        expires_at: When the state, and with it the download, expires; set only when ``status`` is
            ``SUCCEEDED``. A state recorded before this field existed reads as None.
    """

    status: profile_constants.ExportStatus
    error_code: profile_constants.ExportFailure | None = None
    size_bytes: int | None = None
    expires_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _read_stored_state(cls, data: object) -> object:
        """Read a state stored before the shared job vocabulary as the current one."""
        return core_job_status.upgrade_stored_state(data, "failure")


_FINISHED = tuple(core_job_status.TERMINAL_STATES)


class ProfileExportStateStore:
    """Profile export state backed by the platform ``StateProvider``.

    Attributes:
        _ttl_seconds: How long a recorded state lasts.
        _attempts: The claim and state storage for exports.
    """

    def __init__(self, state: StateProvider, ttl_seconds: int = profile_constants.EXPORT_STATE_TTL_SECONDS) -> None:
        """Initialize the export state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long an export's claim and state last.
        """
        self._ttl_seconds = ttl_seconds
        self._attempts = core_attempt_state.AttemptStateStore(
            state, "users", "profile_export", ttl_seconds, announce=websocket_integration.announce_job
        )

    def begin(self, user_id: uuid.UUID, *, conflict: str) -> core_job_status.JobRef:
        """Record an export as queued unless one is still pending.

        Args:
            user_id: The exporting user.
            conflict: The detail of the error for an export already pending.

        Returns:
            The new job's reference.

        Raises:
            JobAlreadyRunningError: When an export is already pending.
            StateUnavailableError: When storage is unavailable.
        """
        return self._attempts.begin(
            str(user_id),
            ProfileExportState(status=profile_constants.ExportStatus.QUEUED),
            kind=profile_constants.EXPORT_JOB,
            owner_id=user_id,
            conflict=conflict,
        )

    def set_status(
        self,
        user_id: uuid.UUID,
        status: profile_constants.ExportStatus,
        *,
        error_code: profile_constants.ExportFailure | None = None,
        size_bytes: int | None = None,
    ) -> None:
        """Record an export's progress or outcome.

        Args:
            user_id: The exporting user.
            status: The new status.
            error_code: Why the export failed, when ``status`` is ``FAILED``.
            size_bytes: The archive size, when ``status`` is ``SUCCEEDED``.

        A completed state is written with a fresh lifetime, so its ``expires_at`` is that lifetime from now.
        """
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=self._ttl_seconds)
            if status == profile_constants.ExportStatus.SUCCEEDED
            else None
        )
        self._attempts.record(
            str(user_id),
            ProfileExportState(status=status, error_code=error_code, size_bytes=size_bytes, expires_at=expires_at),
            finished=status in _FINISHED,
        )

    def get(self, user_id: uuid.UUID) -> ProfileExportState | None:
        """Read a user's export state.

        Args:
            user_id: The exporting user.

        Returns:
            The state, or None when none is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        value = self._attempts.read(str(user_id))
        return ProfileExportState.model_validate_json(value) if value is not None else None

    def read_job(self, job: core_job_status.JobRef) -> tuple[core_job_status.JobRef, ProfileExportState] | None:
        """Read the export a job reference names.

        Args:
            job: The job's reference, from :class:`core.attempt_state.JobIndex`.

        Returns:
            The job's current reference and state, or None when its record is gone or belongs to a later export.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        stored = self._attempts.read_job(job)
        return (stored.job, ProfileExportState.model_validate_json(stored.state_json())) if stored is not None else None
