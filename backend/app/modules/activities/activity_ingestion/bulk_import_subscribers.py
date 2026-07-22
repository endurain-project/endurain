"""Durable-job subscriber that imports one bulk-import file per job (A9).

Bulk import enqueues **one durable job per file** (via the transactional outbox)
instead of a fire-and-forget threadpool task, so a crash mid-import no longer
drops in-flight work and a failing file is retried with backoff and finally
dead-lettered — moved to the import-error directory as the human trail — instead
of vanishing to the error dir on the first error. The job body is the shared sync
ingestion core (A6, :func:`orchestrator.store_bulk_import_file`); the handler
**raises** on failure so the runner retries and eventually dead-letters.

The ``activity.bulk_import_file`` channel is durable-delivery only: the route
publishes it (with the request's db session) exclusively when ``JOBS_ENABLED``,
so it always routes to the outbox → relay → per-file jobs. When durable jobs are
off there is no worker to drain the queue, so the route falls back to the legacy
background threadpool and this event is never published — hence no best-effort bus
subscriber is registered here (only a durable handler).
"""

import os

from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import infra.publisher as platform_publisher
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.orchestrator as orchestrator
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry

# Stable durable-subscriber id (independent of module path) so job history and
# dedup survive refactors.
BULK_IMPORT_FILE_SUBSCRIBER_ID = "activity_ingestion.bulk_import_file"


def publish_bulk_import_file(file_path: str, user_id: int, import_initiated_time: str, db: Session) -> None:
    """Publish one durable bulk-import-file event (one retryable job per file).

    Args:
        file_path: Absolute path to the queued activity file.
        user_id: ID of the user performing the import.
        import_initiated_time: ISO timestamp of when the bulk import was initiated.
        db: The request's database session (the event is staged in the outbox on
            it when durable delivery is enabled).

    Returns:
        None.
    """
    platform_publisher.publish(
        ingestion_events.ACTIVITY_BULK_IMPORT_FILE,
        {"file_path": file_path, "user_id": user_id, "import_initiated_time": import_initiated_time},
        source="api:bulk_import",
        db=db,
    )


def process_bulk_import_file_for_event(event: Event) -> None:
    """Durable handler: import one bulk-import file; raises so the runner retries.

    The durable-job handler for ``activity.bulk_import_file``: any error
    propagates so the runner retries with backoff and eventually dead-letters the
    job. On the final attempt (this failure will dead-letter the job) the
    offending file is moved to the import-error directory first, so a
    dead-lettered file leaves the same human trail as before — but only after the
    retries are exhausted, not on the first error.

    Args:
        event: The ``activity.bulk_import_file`` event (payload
            ``{"file_path": str, "user_id": int, "import_initiated_time": str}``).

    Returns:
        None.
    """
    file_path = event.payload.get("file_path")
    user_id = event.payload.get("user_id")
    import_initiated_time = event.payload.get("import_initiated_time")
    if not isinstance(file_path, str) or not isinstance(user_id, int):
        return
    try:
        with core_database.SessionLocal() as db:
            orchestrator.store_bulk_import_file(user_id, file_path, import_initiated_time, db)
    except Exception:
        # ``retry_count`` is the (claim-incremented) attempt number; when it has
        # reached the ceiling this failure dead-letters the job, so move the file
        # to the import-error directory as the trail before re-raising.
        if event.retry_count >= core_config.settings.JOBS_MAX_ATTEMPTS:
            _move_to_error_dir(file_path)
        raise


def _move_to_error_dir(file_path: str) -> None:
    """Move a dead-lettered bulk-import file to the import-error directory."""
    try:
        error_dir = core_config.FILES_BULK_IMPORT_IMPORT_ERRORS_DIR
        os.makedirs(error_dir, exist_ok=True)
        core_file_uploads.move_within(file_path, error_dir, filename=os.path.basename(file_path))
        core_logger.print_to_log_and_console(
            f"Bulk import: dead-lettered file {file_path} moved to {error_dir}",
            "error",
        )
    except OSError:
        core_logger.print_to_log_and_console(
            f"Bulk import: failed to move dead-lettered file {file_path} to the import-error directory",
            "error",
        )


def register_bulk_import_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the bulk-import-file handler as a durable job subscriber.

    Args:
        registry: The durable-subscriber registry to register on.

    Returns:
        None.
    """
    registry.register(
        ingestion_events.ACTIVITY_BULK_IMPORT_FILE,
        BULK_IMPORT_FILE_SUBSCRIBER_ID,
        process_bulk_import_file_for_event,
    )
