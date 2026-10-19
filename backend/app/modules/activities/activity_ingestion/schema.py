"""Pydantic schemas for the activity ingestion job surface."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

import modules.activities.activity_ingestion.constants as activity_ingestion_constants


class ActivityIngestionJobRead(BaseModel):
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
        import_source: For a bulk import, the archive format it reads.
        files_total: For a bulk import, importable files in its archive.
        files_done: For a bulk import, files imported so far.
        files_failed: For a bulk import, files that could not be imported. A
            finished import with failures still ends ``completed``.
        provider: The one provider a refresh syncs; ``None`` when it syncs every
            linked provider.
        status: Current lifecycle state.
        error_code: Sanitized failure reason when ``status`` is failed.
        activity_ids: Ids created by the import once it completes.
        created_at: When the request was accepted.
        updated_at: When the job last changed state.
        completed_at: When the job reached a terminal state.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    kind: activity_ingestion_constants.IngestionJobKind
    filename: str | None = None
    import_source: str | None = None
    files_total: int | None = None
    files_done: int | None = None
    files_failed: int | None = None
    provider: str | None = None
    status: activity_ingestion_constants.IngestionJobStatus
    error_code: activity_ingestion_constants.IngestionJobErrorCode | None = None
    activity_ids: list[int] = []
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
