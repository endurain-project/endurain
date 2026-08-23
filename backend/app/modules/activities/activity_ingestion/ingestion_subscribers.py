"""Durable-job subscribers for user-initiated ingestion: uploads and refreshes.

Both routes answer 202 and hand the work here, for the same reason: parsing a
file is seconds of pure CPU, and a provider refresh is a chain of third-party
HTTP round-trips. Doing either inline tied up a request thread — and refresh,
being the one ``async`` route, tied up the event loop itself.

Both channels are durable-delivery only: the routes publish them exclusively
when ``JOBS_ENABLED``, so they always route to the outbox → relay → job. When
durable jobs are off the routes fall back to the in-process pool and these
events are never published — hence no best-effort bus subscribers here.

Unlike bulk import, a terminally failed job is **not** moved to an error
directory: the requester is a real client waiting on a status, so the outcome is
recorded on the ``activity_ingestion_jobs`` row where they can read it.
"""

import jasil.event_versioning as platform_event_versioning
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

import core.config as core_config
import core.logger as core_logger
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.ingestion_jobs as ingestion_jobs
import modules.activities.activity_ingestion.schema as activity_ingestion_schema

logger = core_logger.get_logger(__name__)

# Stable durable-subscriber ids (independent of module path) so job history and
# dedup survive refactors.
UPLOADED_FILE_SUBSCRIBER_ID = "activity_ingestion.uploaded_file"
REFRESH_REQUESTED_SUBSCRIBER_ID = "activity_ingestion.refresh_requested"


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

    Returns:
        None.
    """
    payload = platform_event_versioning.parse_payload(ingestion_events.UploadedFilePayload, event)
    try:
        ingestion_jobs.run_upload_job(payload.job_id)
    except Exception as err:
        if _is_final_attempt(event):
            ingestion_jobs.fail_ingestion_job(
                payload.job_id,
                activity_ingestion_schema.IngestionJobErrorCode.PROCESSING_FAILED,
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

    Returns:
        None.
    """
    payload = platform_event_versioning.parse_payload(ingestion_events.RefreshRequestedPayload, event)
    try:
        ingestion_jobs.run_refresh_job(payload.job_id)
    except Exception as err:
        if _is_final_attempt(event):
            ingestion_jobs.fail_ingestion_job(
                payload.job_id,
                activity_ingestion_schema.IngestionJobErrorCode.PROVIDER_UNAVAILABLE,
            )
            logger.error(
                "Refresh job dead-lettered",
                exc_info=err,
                extra=core_logger.context(console=True, job_id=payload.job_id),
            )
        raise


def register_ingestion_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the upload and refresh handlers as durable job subscribers.

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
    registry.register(
        ingestion_events.ACTIVITY_REFRESH_REQUESTED,
        REFRESH_REQUESTED_SUBSCRIBER_ID,
        process_refresh_requested_for_event,
    )
