"""Domain event channel names owned by the activity-ingestion sub-domain."""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published when a bulk import has a batch of its archive left to work through:
# once when the import is accepted, and again at the end of each batch that left
# files over, so every batch is a short job that goes to the back of the queue
# instead of one import holding a worker. Durable-delivery only — without durable
# jobs the import loops in the in-process pool, so no best-effort bus subscriber
# exists for it.
ACTIVITY_BULK_IMPORT_CONTINUE = "activity.bulk_import_continue"


class BulkImportContinuePayload(VersionedPayload):
    """Validated payload for the ``activity.bulk_import_continue`` event.

    Attributes:
        job_id: The ``activity_ingestion_jobs`` row to work the next batch of. The
            owner, archive and resume point are read from the row, never from the
            event.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    job_id: str


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
