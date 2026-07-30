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
        storage_key: Key of the staged file in the bulk-import storage area.
            A key rather than a path so any worker in the fleet can fetch the
            bytes, not only the node the file was dropped on.
        filename: The dropped file's original name. Carried separately because
            the pipeline reads meaning from it (the Strava export's
            ``activities.csv`` is keyed by filename), while the key is minted.
        user_id: ID of the user performing the import.
        import_initiated_time: ISO timestamp of when the import began.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 2

    storage_key: str
    filename: str
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
        job_id: The ``activity_ingestion_jobs`` row to process.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    job_id: str


# Published once per accepted provider refresh when durable jobs are enabled; a
# durable subscriber pulls the linked providers. Durable-delivery only, for the
# same reason as the channels above: the route falls back to the background
# threadpool when JOBS_ENABLED is off, so no best-effort bus subscriber exists.
ACTIVITY_REFRESH_REQUESTED = "activity.refresh_requested"


class RefreshRequestedPayload(VersionedPayload):
    """Validated payload for the ``activity.refresh_requested`` event.

    Carries only the job id, for the same reason as
    :class:`UploadedFilePayload`: the owner is a column on the job row, so a
    tampered payload cannot make the worker sync somebody else's providers.

    Attributes:
        job_id: The ``activity_ingestion_jobs`` row to process.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    job_id: str
