"""Pydantic schemas for the activity ingestion job surface."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class IngestionJobKind(StrEnum):
    """What kind of ingestion the job performs."""

    UPLOAD = "upload"
    REFRESH = "refresh"
    BULK_IMPORT = "bulk_import"


class IngestionJobStatus(StrEnum):
    """Lifecycle states of an ingestion job."""

    PENDING = "pending"
    PROCESSING = "processing"
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


class ActivityIngestionJob(BaseModel):
    """An accepted ingestion request and the current state of its import.

    One shape for all kinds, so a client has a single thing to poll: an upload, a
    bulk-import file and a provider refresh differ in how the activities are
    obtained, not in what the caller needs to know about progress.

    Attributes:
        id: Job identifier, returned by the route that accepted the request.
        kind: Whether this job imports an upload, imports one dropped
            bulk-import file, or syncs from providers.
        filename: Original client filename; only set for uploads and
            bulk-import files.
        status: Current lifecycle state.
        error_code: Sanitized failure reason when ``status`` is failed.
        activity_ids: Ids created by the import once it completes.
        created_at: When the request was accepted.
        updated_at: When the job last changed state.
        completed_at: When the job reached a terminal state.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    kind: IngestionJobKind
    filename: str | None = None
    status: IngestionJobStatus
    error_code: IngestionJobErrorCode | None = None
    activity_ids: list[int] = []
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
