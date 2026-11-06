"""Domain constants for activity ingestion jobs."""

from enum import StrEnum

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
    """Lifecycle states of an ingestion job."""

    PENDING = "pending"
    PROCESSING = "processing"
    DEFERRED = "deferred"
    COMPLETED = "completed"
    FAILED = "failed"


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
