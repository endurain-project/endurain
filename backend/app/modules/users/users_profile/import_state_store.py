"""Shared state of a profile import.

An import is accepted with 202 and runs on a worker, possibly on another replica. The state is
what ``GET /jobs/{job_id}`` reads back, and its claim keeps a user from queueing two imports at
once. It lives in the platform ``StateProvider`` (see :mod:`core.attempt_state`).

Interface::

    begin(user_id, conflict=)               - queue an import, returning its job; raises while one is pending
    set_status(user_id, status, ...)        - record progress or the outcome
    get(user_id)                            - read the current state, or None once expired
    read_job(job)                           - read the import a job reference names
"""

from jasil.providers import StateProvider
from pydantic import BaseModel, model_validator

import core.attempt_state as core_attempt_state
import core.job_status as core_job_status
import modules.users.users_profile.constants as profile_constants
import modules.websocket.integration_service as websocket_integration


class ProfileImportState(BaseModel):
    """The recorded state of one import.

    Attributes:
        status: Where the import is.
        error_code: Why it failed; set only when ``status`` is ``FAILED``.
        imported: How many items of each kind were imported; set only when ``status`` is ``SUCCEEDED``.
    """

    status: profile_constants.ImportStatus
    error_code: profile_constants.ImportFailure | None = None
    imported: dict[str, int] | None = None

    @model_validator(mode="before")
    @classmethod
    def _read_stored_state(cls, data: object) -> object:
        """Read a state stored before the shared job vocabulary as the current one."""
        return core_job_status.upgrade_stored_state(data, "failure")


_FINISHED = (profile_constants.ImportStatus.SUCCEEDED, profile_constants.ImportStatus.FAILED)


class ProfileImportStateStore:
    """Profile import state backed by the platform ``StateProvider``.

    Attributes:
        _attempts: The claim and state storage for imports.
    """

    def __init__(self, state: StateProvider, ttl_seconds: int = profile_constants.IMPORT_STATE_TTL_SECONDS) -> None:
        """Initialize the import state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long an import's claim and state last.
        """
        self._attempts = core_attempt_state.AttemptStateStore(
            state, "users", "profile_import", ttl_seconds, announce=websocket_integration.announce_job
        )

    def begin(self, user_id: int, *, conflict: str) -> core_job_status.JobRef:
        """Record an import as queued unless one is still pending.

        Args:
            user_id: The importing user.
            conflict: The detail of the error for an import already pending.

        Returns:
            The new job's reference.

        Raises:
            JobAlreadyRunningError: When an import is already pending.
            StateUnavailableError: When storage is unavailable.
        """
        return self._attempts.begin(
            str(user_id),
            ProfileImportState(status=profile_constants.ImportStatus.QUEUED),
            kind=profile_constants.IMPORT_JOB,
            owner_id=user_id,
            conflict=conflict,
        )

    def discard(self, user_id: int) -> None:
        """Forget an import that was refused before it started, so the user can try again at once.

        Args:
            user_id: The importing user.
        """
        self._attempts.discard(str(user_id))

    def set_status(
        self,
        user_id: int,
        status: profile_constants.ImportStatus,
        *,
        error_code: profile_constants.ImportFailure | None = None,
        imported: dict[str, int] | None = None,
        strict: bool = False,
    ) -> None:
        """Record an import's progress or outcome.

        Args:
            user_id: The importing user.
            status: The new status.
            error_code: Why the import failed, when ``status`` is ``FAILED``.
            imported: The counts of what was imported, when ``status`` is ``SUCCEEDED``.
            strict: Raise when the state cannot be recorded, instead of logging it.

        Raises:
            StateUnavailableError: When ``strict`` and storage is unavailable.
        """
        self._attempts.record(
            str(user_id),
            ProfileImportState(status=status, error_code=error_code, imported=imported),
            finished=status in _FINISHED,
            strict=strict,
        )

    def get(self, user_id: int) -> ProfileImportState | None:
        """Read a user's import state.

        Args:
            user_id: The importing user.

        Returns:
            The state, or None when none is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        value = self._attempts.read(str(user_id))
        return ProfileImportState.model_validate_json(value) if value is not None else None

    def read_job(self, job: core_job_status.JobRef) -> tuple[core_job_status.JobRef, ProfileImportState] | None:
        """Read the import a job reference names.

        Args:
            job: The job's reference, from :class:`core.attempt_state.JobIndex`.

        Returns:
            The job's current reference and state, or None when its record is gone or belongs to a later import.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        stored = self._attempts.read_job(job)
        return (stored.job, ProfileImportState.model_validate_json(stored.state_json())) if stored is not None else None
