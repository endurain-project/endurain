"""Durable-job subscribers for activity ingestion: uploads, refreshes and bulk imports.

The upload and refresh routes answer 202 and hand the work here, because parsing
a file is seconds of pure CPU and a provider refresh is a chain of third-party
HTTP round-trips, neither of which belongs on a request thread.

A bulk import is one job over one staged archive, worked through in short batches
that each queue the next, so a large import interleaves with other work and resumes
from its cursor after a crash.

Every channel is durable-delivery only: the routes publish them exclusively when
``JOBS_ENABLED``, so they always route to the outbox -> relay -> job. When durable
jobs are off the routes fall back to the in-process pool and these events are
never published — hence no best-effort bus subscribers here.

The handlers **raise** on failure so the runner retries and eventually
dead-letters. The outcome a client reads is recorded on the
``activity_ingestion_jobs`` row.
"""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

import core.config as core_config
import core.logger as core_logger
import modules.activities.activity_ingestion.bulk_import_service as activity_ingestion_bulk_import_service
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.events as activity_ingestion_events
import modules.activities.activity_ingestion.service as activity_ingestion_service

logger = core_logger.get_logger(__name__)

# Stable durable-subscriber ids (independent of module path) so job history and
# dedup survive refactors.
UPLOADED_FILE_SUBSCRIBER_ID = "activity_ingestion.uploaded_file"
REFRESH_REQUESTED_SUBSCRIBER_ID = "activity_ingestion.refresh_requested"
BULK_IMPORT_SUBSCRIBER_ID = "activity_ingestion.bulk_import"


def _is_final_attempt(event: Event) -> bool:
    """Whether this failure will dead-letter the job.

    ``retry_count`` is the claim-incremented attempt number, so reaching the
    ceiling means the runner has no attempts left.

    Args:
        event: The event being processed.

    Returns:
        True when no further retry will happen.
    """
    return event.retry_count >= core_config.settings.JOBS_MAX_ATTEMPTS


def process_uploaded_file_for_event(event: Event) -> None:
    """Durable handler: import one uploaded file; raises so the runner retries.

    On the final attempt the job row is marked failed before re-raising, so a
    dead-lettered upload still ends in a terminal state the uploader can see
    rather than sitting at ``processing`` forever.

    Args:
        event: The ``activity.file_uploaded`` event (payload ``{"job_id": str}``).
    """
    payload = platform_event_versioning.parse_payload(activity_ingestion_events.UploadedFilePayload, event)
    storage = platform_runtime.get_active_platform().storage
    try:
        activity_ingestion_service.run_upload_job(payload.job_id, storage)
    except Exception as err:
        if _is_final_attempt(event):
            activity_ingestion_service.fail_ingestion_job(
                payload.job_id,
                activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
                storage,
            )
            logger.error(
                "Upload job dead-lettered",
                exc_info=err,
                extra=core_logger.context(console=True, job_id=payload.job_id),
            )
        raise


def process_refresh_requested_for_event(event: Event) -> None:
    """Durable handler: sync one user's providers; raises so the runner retries.

    Provider failures are the common case here — a rate limit, an expired token,
    an outage — and all of them are worth retrying with backoff, which is why
    nothing is treated as terminal until the attempts run out.

    Args:
        event: The ``activity.refresh_requested`` event (payload
            ``{"job_id": str}``).
    """
    payload = platform_event_versioning.parse_payload(activity_ingestion_events.RefreshRequestedPayload, event)
    storage = platform_runtime.get_active_platform().storage
    try:
        activity_ingestion_service.run_refresh_job(payload.job_id, storage)
    except Exception as err:
        if _is_final_attempt(event):
            activity_ingestion_service.fail_ingestion_job(
                payload.job_id,
                activity_ingestion_constants.IngestionJobErrorCode.PROVIDER_UNAVAILABLE,
                storage,
            )
            logger.error(
                "Refresh job dead-lettered",
                exc_info=err,
                extra=core_logger.context(console=True, job_id=payload.job_id),
            )
        raise


def process_bulk_import_for_event(event: Event) -> None:
    """Durable handler: work one batch of a bulk import; raises so the runner retries.

    The batch records its progress on the job row, and queues its own continuation
    when it leaves files over, so a retry resumes from the cursor rather than from
    the start. On the final attempt the job is closed as failed so the owner sees a
    terminal state instead of ``processing`` forever.

    Args:
        event: The ``activity.bulk_import_continue`` event (payload
            ``{"job_id": str}``).
    """
    payload = platform_event_versioning.parse_payload(activity_ingestion_events.BulkImportContinuePayload, event)
    storage = platform_runtime.get_active_platform().storage
    try:
        activity_ingestion_bulk_import_service.run_bulk_import_job(payload.job_id, storage)
    except Exception as err:
        if _is_final_attempt(event):
            activity_ingestion_service.fail_ingestion_job(
                payload.job_id,
                activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
                storage,
            )
            logger.error(
                "Bulk import dead-lettered",
                exc_info=err,
                extra=core_logger.context(console=True, job_id=payload.job_id),
            )
        raise


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the ingestion handlers as durable job subscribers.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        activity_ingestion_events.ACTIVITY_FILE_UPLOADED,
        UPLOADED_FILE_SUBSCRIBER_ID,
        process_uploaded_file_for_event,
    )
    registry.register(
        activity_ingestion_events.ACTIVITY_REFRESH_REQUESTED,
        REFRESH_REQUESTED_SUBSCRIBER_ID,
        process_refresh_requested_for_event,
    )
    registry.register(
        activity_ingestion_events.ACTIVITY_BULK_IMPORT_CONTINUE,
        BULK_IMPORT_SUBSCRIBER_ID,
        process_bulk_import_for_event,
    )
