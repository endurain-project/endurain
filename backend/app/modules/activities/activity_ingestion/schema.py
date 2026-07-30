"""Pydantic schemas for the activity upload job surface."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class UploadJobStatus(StrEnum):
    """Lifecycle states of an upload job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadJobErrorCode(StrEnum):
    """Stable, sanitized reasons an upload job can fail.

    Deliberately a closed set. The underlying exception text can carry
    filesystem paths and parser internals, so the client is given a code it can
    translate instead of a message the server happened to produce.
    """

    UNSUPPORTED_FORMAT = "unsupported_format"
    INVALID_FILE = "invalid_file"
    NO_ACTIVITIES_FOUND = "no_activities_found"
    PROCESSING_FAILED = "processing_failed"


class ActivityUploadJob(BaseModel):
    """An accepted upload and the current state of its import.

    Attributes:
        id: Upload job identifier, returned by the upload route.
        filename: Original client filename, echoed back for display.
        status: Current lifecycle state.
        error_code: Sanitized failure reason when ``status`` is failed.
        activity_ids: Ids created by the import once it completes.
        created_at: When the upload was accepted.
        updated_at: When the job last changed state.
        completed_at: When the job reached a terminal state.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: UploadJobStatus
    error_code: UploadJobErrorCode | None = None
    activity_ids: list[int] = []
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
