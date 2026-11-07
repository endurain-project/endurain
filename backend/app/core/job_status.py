"""The status every background job reports, whatever the job is.

An upload, a bulk import, a provider sync, a Garmin Connect link, a bulk edit, an account deletion and a profile
export or import are all accepted with ``202`` and polled. They share this envelope so a client reads one
``status`` vocabulary, one failure field and one set of timestamps; each kind adds only its own fields on a
subclass.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobState(StrEnum):
    """Where a background job is.

    Attributes:
        QUEUED: Accepted, not started, or waiting to run again.
        RUNNING: A worker is doing it.
        SUCCEEDED: Finished and did what was asked.
        FAILED: Finished without doing it; ``error_code`` says why when the kind records a reason.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


#: The states that end a job: a poll sends no ``Retry-After`` once a status reports one.
TERMINAL_STATES = frozenset({JobState.SUCCEEDED, JobState.FAILED})


def upgrade_stored_state(data: object, error_key: str | None = None) -> object:
    """Read a job state stored before the shared vocabulary as the current one.

    A state lives in the platform state provider for up to a few hours, so one written by the previous release can
    still be there after an upgrade. ``completed`` is ``succeeded``, and the failure field the old shape called
    ``error_key`` is ``error_code``. Any other value passes through unchanged, so the model validates it as usual.

    Args:
        data: The stored value, as the model is about to validate it.
        error_key: The old name of the failure field, if the kind had one.

    Returns:
        The value in the current shape.
    """
    if not isinstance(data, dict):
        return data
    upgraded = dict(data)
    if upgraded.get("status") == "completed":
        upgraded["status"] = JobState.SUCCEEDED.value
    if error_key is not None and error_key in upgraded:
        upgraded.setdefault("error_code", upgraded.pop(error_key))
    return upgraded


class JobStatus(BaseModel):
    """The envelope of every background job's status.

    Attributes:
        id: The job's identifier, for a job that has one of its own; ``null`` for work that is one per user and
            kind, which is polled by that kind's status route alone.
        status: Where the job is.
        error_code: Why the job failed, from a closed set per kind; ``null`` unless ``status`` is ``failed`` and
            the kind records a reason.
        created_at: When the job was accepted, for a kind that records it.
        finished_at: When the job reached ``succeeded`` or ``failed``, for a kind that records it.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, description="The job's identifier, when it has one of its own")
    status: JobState = Field(..., description="Where the job is")
    error_code: str | None = Field(default=None, description="Why the job failed; null unless it failed")
    created_at: datetime | None = Field(default=None, description="When the job was accepted")
    finished_at: datetime | None = Field(default=None, description="When the job succeeded or failed")
