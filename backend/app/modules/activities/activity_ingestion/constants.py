"""Domain constants for activity ingestion jobs."""

from enum import StrEnum

import core.job_status as core_job_status

#: Storage area holding the files a bulk import could not read, for the operator.
BULK_IMPORT_ERROR_STORAGE_AREA = "bulk_import_errors"

#: The name of the route that reads an ingestion job, which every ``202`` that returns a job points at.
JOB_STATUS_ROUTE = "read_activity_ingestion_job"


class IngestionJobKind(StrEnum):
    """What kind of ingestion the job performs."""

    UPLOAD = "upload"
    REFRESH = "refresh"
    BULK_IMPORT = "bulk_import"


#: Seconds a client waits before polling a job of each kind: an upload parses in seconds, a refresh or an
#: archive import takes longer.
JOB_POLL_SECONDS: dict[IngestionJobKind, int] = {
    IngestionJobKind.UPLOAD: 2,
    IngestionJobKind.REFRESH: 5,
    IngestionJobKind.BULK_IMPORT: 5,
}


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
