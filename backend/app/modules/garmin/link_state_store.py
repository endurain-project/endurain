"""Shared state of a Garmin Connect link attempt.

Linking logs in to Garmin in a background thread that may wait for an MFA code, while the
browser polls ``GET /jobs/{job_id}``. The poll can land on any replica, so the
state lives in the platform ``StateProvider`` (see :mod:`core.attempt_state`). The state
is the contract: the browser learns that an MFA code is wanted by reading it, never from a push
that could be lost.

Interface::

    begin(user_id, conflict=...)   - start an attempt as a job; raises while one is still running
    set_status(user_id, status)    - record progress or the outcome
    get(user_id)                   - read the current state, or None once expired
    current_job(user_id)           - the job of the current attempt, or None once expired
    read_job(job)                  - read the state of the job a reference names
"""

import uuid

from jasil.providers import StateProvider
from pydantic import BaseModel, model_validator

import core.attempt_state as core_attempt_state
import core.job_status as core_job_status
import modules.garmin.constants as garmin_constants
import modules.websocket.integration_service as websocket_integration


class LinkState(BaseModel):
    """The recorded state of one link attempt.

    Attributes:
        status: Where the attempt is; ``RUNNING`` for the whole login, including while it waits for an MFA code.
        mfa_required: Whether the login waits for the user's MFA code.
        error_code: Why it failed; set only when ``status`` is ``FAILED``.
    """

    status: core_job_status.JobState
    mfa_required: bool = False
    error_code: garmin_constants.LinkFailure | None = None

    @model_validator(mode="before")
    @classmethod
    def _read_stored_state(cls, data: object) -> object:
        """Read a state stored before the shared job vocabulary as the current one.

        ``pending`` was the login in progress and ``mfa_required`` the login waiting for a code; both are
        ``running`` now, the second with ``mfa_required`` set.
        """
        data = core_job_status.upgrade_stored_state(data, "reason")
        if isinstance(data, dict) and data.get("status") in ("pending", "mfa_required"):
            data = {
                **data,
                "mfa_required": data["status"] == "mfa_required",
                "status": core_job_status.JobState.RUNNING.value,
            }
        return data


_FINISHED = tuple(core_job_status.TERMINAL_STATES)


class GarminLinkStateStore:
    """Garmin link attempt state backed by the platform ``StateProvider``.

    Attributes:
        _attempts: The claim and state storage for link attempts.
    """

    def __init__(self, state: StateProvider, ttl_seconds: int = garmin_constants.LINK_TTL_SECONDS) -> None:
        """Initialize the link state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long a link attempt's claim and state last.
        """
        self._attempts = core_attempt_state.AttemptStateStore(
            state, "garmin", "link", ttl_seconds, announce=websocket_integration.announce_job
        )

    def begin(self, user_id: uuid.UUID, *, conflict: str) -> core_job_status.JobRef:
        """Start a link attempt as a job unless one is still running.

        A finished attempt releases the claim, so the user can retry straight after a failure.

        Args:
            user_id: Authenticated user ID.
            conflict: The detail of the error for an attempt already running.

        Returns:
            The new job's reference.

        Raises:
            JobAlreadyRunningError: When another attempt is in progress.
            StateUnavailableError: When storage is unavailable.
        """
        return self._attempts.begin(
            str(user_id),
            LinkState(status=core_job_status.JobState.RUNNING),
            kind=garmin_constants.LINK_JOB,
            owner_id=user_id,
            conflict=conflict,
        )

    def release(self, user_id: uuid.UUID) -> None:
        """Abandon an attempt that never got to run, so the user can retry at once.

        Args:
            user_id: Authenticated user ID.
        """
        self._attempts.release(str(user_id))

    def set_status(
        self,
        user_id: uuid.UUID,
        status: core_job_status.JobState,
        error_code: garmin_constants.LinkFailure | None = None,
        *,
        mfa_required: bool = False,
    ) -> None:
        """Record a link attempt's progress or outcome.

        Args:
            user_id: Authenticated user ID.
            status: The new status.
            error_code: Why the attempt failed, when ``status`` is ``FAILED``.
            mfa_required: Whether the login now waits for the user's MFA code.
        """
        self._attempts.record(
            str(user_id),
            LinkState(status=status, mfa_required=mfa_required, error_code=error_code),
            finished=status in _FINISHED,
        )

    def get(self, user_id: uuid.UUID) -> LinkState | None:
        """Read a user's link attempt state.

        Args:
            user_id: Authenticated user ID.

        Returns:
            The state, or None when no attempt is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        value = self._attempts.read(str(user_id))
        return LinkState.model_validate_json(value) if value is not None else None

    def current_job(self, user_id: uuid.UUID) -> core_job_status.JobRef | None:
        """Read the job of a user's current link attempt.

        Args:
            user_id: Authenticated user ID.

        Returns:
            The job's reference, or None when no attempt is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        stored = self._attempts.read_stored(str(user_id))
        return stored.job if stored is not None else None

    def read_job(self, job: core_job_status.JobRef) -> tuple[core_job_status.JobRef, LinkState] | None:
        """Read the link attempt a job reference names.

        Args:
            job: The job's reference.

        Returns:
            The job's current reference and state, or None when its record is gone or belongs to a later attempt.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        stored = self._attempts.read_job(job)
        return (stored.job, LinkState.model_validate_json(stored.state_json())) if stored is not None else None
