"""Domain constants for activity ingestion jobs."""

import uuid
from enum import StrEnum
from typing import Literal, Self

import core.job_status as core_job_status

#: Storage area holding the files a bulk import could not read, for the operator.
BULK_IMPORT_ERROR_STORAGE_AREA = "bulk_import_errors"


def bulk_import_error_root(user_id: uuid.UUID) -> str:
    """Return the storage path that holds one user's failed bulk-import files.

    ``StorageProvider.delete_prefix`` takes this path, not a prefix ending in ``/``: it removes the object at the path
    and every object under ``<path>/``, so another user's keys are never reached.

    Args:
        user_id: The user the failed files belong to.

    Returns:
        The path, ``"<user_id>"``.
    """
    return str(user_id)


def bulk_import_error_prefix(user_id: uuid.UUID) -> str:
    """Return the key prefix under which one user's failed bulk-import files are stored.

    Args:
        user_id: The user the failed files belong to.

    Returns:
        The prefix, ``"<user_id>/"``.
    """
    return f"{bulk_import_error_root(user_id)}/"


#: Seconds a scheduled fan-out waits for a free slot in the local pool before it fails a refresh. The pool
#: holds far fewer jobs than a large install has linked users, so the overflow waits for the jobs ahead to finish.
SCHEDULED_SLOT_WAIT_SECONDS = 300

#: The most uploads one user may have open (pending, processing or deferred) at once.
MAX_OPEN_UPLOADS_PER_USER = 10

#: The job kinds a client reads for an ingestion job, as ``GET /jobs/{job_id}`` names them.
JobKindName = Literal["activity_upload", "activity_refresh", "activity_bulk_import"]


class IngestionJobKind(StrEnum):
    """What kind of ingestion the job performs."""

    UPLOAD = "upload"
    REFRESH = "refresh"
    BULK_IMPORT = "bulk_import"

    @property
    def job_kind(self) -> JobKindName:
        """The kind a client reads: the stored kind under the ``activity_`` prefix."""
        return _JOB_KIND_NAMES[self]

    @classmethod
    def from_job_kind(cls, job_kind: str) -> Self:
        """Return the stored kind a client-facing job kind names.

        Args:
            job_kind: A client-facing kind such as ``activity_upload``.

        Returns:
            The stored kind.

        Raises:
            ValueError: When ``job_kind`` names no ingestion kind.
        """
        return cls(job_kind.removeprefix(_JOB_KIND_PREFIX))


_JOB_KIND_PREFIX = "activity_"

_JOB_KIND_NAMES: dict[IngestionJobKind, JobKindName] = {
    IngestionJobKind.UPLOAD: "activity_upload",
    IngestionJobKind.REFRESH: "activity_refresh",
    IngestionJobKind.BULK_IMPORT: "activity_bulk_import",
}


#: Seconds a client waits before polling a job of each kind: an upload parses in seconds, a refresh or an
#: archive import takes longer.
JOB_POLL_SECONDS: dict[IngestionJobKind, int] = {
    IngestionJobKind.UPLOAD: 2,
    IngestionJobKind.REFRESH: 5,
    IngestionJobKind.BULK_IMPORT: 5,
}


def job_poll_seconds(job_kind: str) -> int:
    """Return the seconds a client waits before the first poll of a job it reads under ``job_kind``.

    Args:
        job_kind: The client-facing kind of the job, such as ``activity_upload``.

    Returns:
        The wait in seconds.

    Raises:
        ValueError: When ``job_kind`` names no ingestion kind.
    """
    return JOB_POLL_SECONDS[IngestionJobKind.from_job_kind(job_kind)]


class IngestionJobStatus(StrEnum):
    """Lifecycle states an ingestion job's row records; a client reads them as a :class:`JobState`."""

    PENDING = "pending"
    PROCESSING = "processing"
    DEFERRED = "deferred"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def job_state(self) -> core_job_status.JobState:
        """The state a client is told: a deferred refresh is queued again, and ``retry_after`` says when."""
        return _JOB_STATES[self]


_JOB_STATES = {
    IngestionJobStatus.PENDING: core_job_status.JobState.QUEUED,
    IngestionJobStatus.PROCESSING: core_job_status.JobState.RUNNING,
    IngestionJobStatus.DEFERRED: core_job_status.JobState.QUEUED,
    IngestionJobStatus.COMPLETED: core_job_status.JobState.SUCCEEDED,
    IngestionJobStatus.FAILED: core_job_status.JobState.FAILED,
}


def statuses_for_state(state: core_job_status.JobState) -> list[IngestionJobStatus]:
    """Return the stored statuses a client reads as a job state.

    Args:
        state: The state a client filters by.

    Returns:
        The stored statuses that map to it.
    """
    return [status for status, mapped in _JOB_STATES.items() if mapped == state]


class IngestionJobErrorCode(StrEnum):
    """Stable, sanitized reasons an ingestion job can fail.

    Deliberately a closed set. The underlying exception text can carry
    filesystem paths, parser internals and provider tokens, so the client is
    given a code it can translate instead of a message the server happened to
    produce.
    """

    UNSUPPORTED_FORMAT = "unsupported_format"
    INVALID_FILE = "invalid_file"
    NO_ACTIVITIES_FOUND = "no_activities_found"
    PROCESSING_FAILED = "processing_failed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
