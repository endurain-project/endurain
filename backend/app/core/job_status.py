"""The status every background job reports, whatever the job is.

An upload, a bulk import, a provider sync, a Garmin Connect link, a bulk edit, an account deletion and a profile
export or import are all accepted with ``202`` and polled at ``GET /jobs/{job_id}``. They share this envelope
so a client reads one id, one ``status`` vocabulary, one failure field and one set of timestamps; each kind adds
only its own fields on a subclass.
"""

import uuid
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


#: The name of the route that reads a job by id, ``GET /jobs/{job_id}``; a ``202`` and a refused second start
#: point at it.
JOB_ROUTE = "read_job"

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


class JobRef(BaseModel):
    """What a job id names: the kind of work, who may read it and where its record is kept.

    The platform state store indexes it by id, so ``GET /jobs/{job_id}`` finds the kind's record without
    knowing the feature that owns it.

    Attributes:
        id: The job's identifier, a UUIDv4 string.
        kind: What the job does, e.g. ``garmin_link``; one value per kind of work across the application.
        owner_id: The user who started the job and may read it.
        subject: Whose record it is in the owning feature's store, e.g. ``"<user id>:gear"``.
        created_at: When the job was accepted.
        finished_at: When the job reached ``succeeded`` or ``failed``.
    """

    id: str
    kind: str
    owner_id: uuid.UUID
    subject: str
    created_at: datetime
    finished_at: datetime | None = None

    def envelope(self) -> dict[str, object]:
        """Return the fields of :class:`JobStatus` this reference fills.

        Returns:
            The id, kind and timestamps, to build a kind's status model with.
        """
        return {"id": self.id, "kind": self.kind, "created_at": self.created_at, "finished_at": self.finished_at}


class JobStatus(BaseModel):
    """The envelope of every background job's status.

    A kind subclasses it, narrows ``kind`` to its own values and adds its own fields; ``kind`` tells the
    subclasses apart in ``GET /jobs/{job_id}``.

    Attributes:
        id: The job's identifier; ``GET /jobs/{job_id}`` reads it.
        kind: What the job does.
        status: Where the job is.
        error_code: Why the job failed, from a closed set per kind; ``null`` unless ``status`` is ``failed`` and
            the kind records a reason.
        created_at: When the job was accepted.
        finished_at: When the job reached ``succeeded`` or ``failed``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="The job's identifier")
    kind: str = Field(..., description="What the job does")
    status: JobState = Field(..., description="Where the job is")
    error_code: str | None = Field(default=None, description="Why the job failed; null unless it failed")
    created_at: datetime = Field(..., description="When the job was accepted")
    finished_at: datetime | None = Field(default=None, description="When the job succeeded or failed")
