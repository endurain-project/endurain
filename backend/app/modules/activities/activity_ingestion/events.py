"""Domain event channel names owned by the activity-ingestion sub-domain."""

from typing import ClassVar

from pydantic import ConfigDict

from infra.event_versioning import VersionedPayload

# Published once per file when a bulk import is initiated with durable jobs
# enabled; a durable subscriber imports each file as an independent,
# retryable, dead-letterable job. This channel is durable-delivery only — the
# route only publishes it when JOBS_ENABLED (so it always routes to the outbox →
# relay → per-file jobs), and falls back to the background threadpool otherwise,
# so no best-effort bus subscriber exists for it.
ACTIVITY_BULK_IMPORT_FILE = "activity.bulk_import_file"


class BulkImportFilePayload(VersionedPayload):
    """Validated payload for the ``activity.bulk_import_file`` event.

    The durable subscriber validates the event payload against this schema, so a
    malformed payload raises (surfacing via retry / dead-letter) instead of
    silently marking the job complete.

    Attributes:
        file_path: Absolute path to the queued activity file.
        user_id: ID of the user performing the import.
        import_initiated_time: ISO timestamp of when the import began.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    file_path: str
    user_id: int
    import_initiated_time: str | None = None


# Published once per accepted upload when durable jobs are enabled; a durable
# subscriber parses the staged file as an independent, retryable job. Like the
# bulk-import channel this is durable-delivery only — the route falls back to
# the background threadpool when JOBS_ENABLED is off, so no best-effort bus
# subscriber exists for it.
ACTIVITY_FILE_UPLOADED = "activity.file_uploaded"


class UploadedFilePayload(VersionedPayload):
    """Validated payload for the ``activity.file_uploaded`` event.

    Carries only the upload job id: the staged path and owner are columns on the
    job row, so the worker reads them under the same ownership check the HTTP
    surface uses and a tampered payload cannot redirect the parse at a file the
    uploader does not own.

    Attributes:
        job_id: The ``activity_upload_jobs`` row to process.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    job_id: str
