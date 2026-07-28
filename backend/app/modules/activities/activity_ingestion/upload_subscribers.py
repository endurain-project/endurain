"""Durable-job subscriber that imports one uploaded activity file per job.

The upload route answers 202 as soon as the bytes are on disk and hands the
parse to a background worker, because parsing is seconds of pure CPU and running
it inline held one of Starlette's shared threadpool tokens for the duration.

The ``activity.file_uploaded`` channel is durable-delivery only: the route
publishes it exclusively when ``JOBS_ENABLED``, so it always routes to the
outbox → relay → per-upload job. When durable jobs are off the route falls back
to the in-process pool and this event is never published — hence no best-effort
bus subscriber is registered here (only a durable handler).

Unlike bulk import, a terminally failed upload is **not** moved to an error
directory: the uploader is a real client waiting on a status, so the outcome is
recorded on the ``activity_upload_jobs`` row where they can read it.
"""

import core.config as core_config
import core.logger as core_logger
import infra.event_versioning as platform_event_versioning
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.upload_jobs as upload_jobs
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry

logger = core_logger.get_logger(__name__)

# Stable durable-subscriber id (independent of module path) so job history and
# dedup survive refactors.
UPLOADED_FILE_SUBSCRIBER_ID = "activity_ingestion.uploaded_file"


def process_uploaded_file_for_event(event: Event) -> None:
    """Durable handler: import one uploaded file; raises so the runner retries.

    On the final attempt the job row is marked failed before re-raising, so a
    dead-lettered upload still ends in a terminal state the uploader can see
    rather than sitting at ``processing`` forever.

    Args:
        event: The ``activity.file_uploaded`` event (payload ``{"job_id": str}``).

    Returns:
        None.
    """
    payload = platform_event_versioning.parse_payload(ingestion_events.UploadedFilePayload, event)
    try:
        upload_jobs.run_upload_job(payload.job_id)
    except Exception:
        # ``retry_count`` is the (claim-incremented) attempt number; when it has
        # reached the ceiling this failure dead-letters the job, so give the
        # uploader a terminal status before re-raising.
        if event.retry_count >= core_config.settings.JOBS_MAX_ATTEMPTS:
            upload_jobs.fail_upload_job(
                payload.job_id,
                activity_ingestion_schema.UploadJobErrorCode.PROCESSING_FAILED,
            )
            logger.error(
                "Upload job dead-lettered",
                extra=core_logger.context(console=True, job_id=payload.job_id),
            )
        raise


def register_upload_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the uploaded-file handler as a durable job subscriber.

    Args:
        registry: The durable-subscriber registry to register on.

    Returns:
        None.
    """
    registry.register(
        ingestion_events.ACTIVITY_FILE_UPLOADED,
        UPLOADED_FILE_SUBSCRIBER_ID,
        process_uploaded_file_for_event,
    )
