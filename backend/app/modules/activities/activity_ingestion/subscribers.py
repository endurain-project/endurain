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
from jasil.event_versioning import VersionedPayload
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

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


def process_uploaded_file_for_event(event: Event) -> None:
    """Durable handler: import one uploaded file; raises so the runner retries.

    Args:
        event: The ``activity.file_uploaded`` event (payload ``{"job_id": str}``).
    """
    payload = platform_event_versioning.parse_payload(activity_ingestion_events.UploadedFilePayload, event)
    storage = platform_runtime.get_active_platform().storage
    activity_ingestion_service.run_upload_job(payload.job_id, storage)
    logger.debug("Upload job finished", extra=core_logger.context(job_id=payload.job_id))


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
    activity_ingestion_service.run_refresh_job(payload.job_id, storage)
    logger.debug("Refresh job finished", extra=core_logger.context(job_id=payload.job_id))


def process_bulk_import_for_event(event: Event) -> None:
    """Durable handler: work one batch of a bulk import; raises so the runner retries.

    The batch records its progress on the job row, and queues its own continuation
    when it leaves files over, so a retry resumes from the cursor rather than from
    the start.

    Args:
        event: The ``activity.bulk_import_continue`` event (payload
            ``{"job_id": str}``).
    """
    payload = platform_event_versioning.parse_payload(activity_ingestion_events.BulkImportContinuePayload, event)
    storage = platform_runtime.get_active_platform().storage
    activity_ingestion_bulk_import_service.run_bulk_import_job(payload.job_id, storage)
    logger.debug("Bulk import batch finished", extra=core_logger.context(job_id=payload.job_id))


def _close_dead_lettered_job(
    event: Event,
    payload_type: type[VersionedPayload],
    error_code: activity_ingestion_constants.IngestionJobErrorCode,
    error: str | None,
) -> None:
    """Close a job the runner gave up on, so its owner sees a terminal state rather than ``processing``.

    Runs whether the last attempt raised, its lease expired or the worker died, and may run more than
    once; closing a job that is already terminal does nothing.

    Args:
        event: The event of the dead-lettered job.
        payload_type: The payload model of the event.
        error_code: The sanitized reason the owner sees.
        error: What the runner recorded, for the log only.
    """
    payload = platform_event_versioning.parse_payload(payload_type, event)
    storage = platform_runtime.get_active_platform().storage
    activity_ingestion_service.fail_ingestion_job(payload.job_id, error_code, storage)
    logger.error(
        "An ingestion job was dead-lettered",
        extra=core_logger.context(
            console=True, job_id=payload.job_id, event_type=event.event_type, attempts=event.max_attempts, error=error
        ),
    )


def on_uploaded_file_dead_letter(event: Event, error: str | None) -> None:
    """Close an upload the runner gave up on.

    Args:
        event: The ``activity.file_uploaded`` event.
        error: What the runner recorded.
    """
    _close_dead_lettered_job(
        event,
        activity_ingestion_events.UploadedFilePayload,
        activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
        error,
    )


def on_refresh_requested_dead_letter(event: Event, error: str | None) -> None:
    """Close a provider refresh the runner gave up on.

    Args:
        event: The ``activity.refresh_requested`` event.
        error: What the runner recorded.
    """
    _close_dead_lettered_job(
        event,
        activity_ingestion_events.RefreshRequestedPayload,
        activity_ingestion_constants.IngestionJobErrorCode.PROVIDER_UNAVAILABLE,
        error,
    )


def on_bulk_import_dead_letter(event: Event, error: str | None) -> None:
    """Close a bulk import the runner gave up on.

    Args:
        event: The ``activity.bulk_import_continue`` event.
        error: What the runner recorded.
    """
    _close_dead_lettered_job(
        event,
        activity_ingestion_events.BulkImportContinuePayload,
        activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
        error,
    )


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the ingestion handlers as durable job subscribers.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        activity_ingestion_events.ACTIVITY_FILE_UPLOADED,
        UPLOADED_FILE_SUBSCRIBER_ID,
        process_uploaded_file_for_event,
        on_dead_letter=on_uploaded_file_dead_letter,
    )
    registry.register(
        activity_ingestion_events.ACTIVITY_REFRESH_REQUESTED,
        REFRESH_REQUESTED_SUBSCRIBER_ID,
        process_refresh_requested_for_event,
        on_dead_letter=on_refresh_requested_dead_letter,
    )
    registry.register(
        activity_ingestion_events.ACTIVITY_BULK_IMPORT_CONTINUE,
        BULK_IMPORT_SUBSCRIBER_ID,
        process_bulk_import_for_event,
        on_dead_letter=on_bulk_import_dead_letter,
    )
