"""Durable-job subscriber that imports one bulk-import file per job.

Bulk import enqueues **one durable job per file** (via the transactional outbox)
instead of a fire-and-forget threadpool task, so a crash mid-import no longer
drops in-flight work and a failing file is retried with backoff and finally
dead-lettered — moved to the import-error directory as the human trail — instead
of vanishing to the error dir on the first error. The job body is the shared sync
ingestion core (:func:`bulk_entry.store_bulk_import_file`); the handler
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
import modules.activities.activity_ingestion.bulk_entry as bulk_entry
import modules.activities.activity_ingestion.events as ingestion_events
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry

logger = core_logger.get_logger(__name__)

# Stable durable-subscriber id (independent of module path) so job history and
# dedup survive refactors.
BULK_IMPORT_FILE_SUBSCRIBER_ID = "activity_ingestion.bulk_import_file"


def publish_bulk_import_files(
    file_paths: list[str],
    user_id: int,
    import_initiated_time: str,
    db: Session,
) -> None:
    """Enqueue one durable bulk-import job per file, in a single transaction.

    Unlike every other publish in the activities domain, this event **is** the
    work rather than a notification about work already done: nothing else records
    the intent to import the file, and the subscriber is deliberately
    reconciliation-net exempt (a dead-lettered file is recovered by re-adding it
    to the bulk-import directory, not by a sweeper). A swallowed publish failure
    would therefore mean the file is silently never imported while the route still
    answers 202 — so this goes through
    :func:`infra.publisher.publish_many_committing`, which **propagates** staging
    failures instead of logging and continuing.

    Staging the whole batch in one transaction also replaces the previous
    one-commit-per-file loop, so enqueuing a large export is a single commit
    rather than thousands inside one request.

    Args:
        file_paths: Absolute paths to the queued activity files.
        user_id: ID of the user performing the import.
        import_initiated_time: ISO timestamp of when the bulk import was initiated.
        db: The request's database session (the outbox rows are staged on it).

    Returns:
        None.

    Raises:
        Exception: Propagated from the outbox staging so the caller can fail the
            request instead of reporting a false success.
    """
    platform_publisher.publish_many_committing(
        ingestion_events.ACTIVITY_BULK_IMPORT_FILE,
        [
            {"file_path": file_path, "user_id": user_id, "import_initiated_time": import_initiated_time}
            for file_path in file_paths
        ],
        source="api:bulk_import",
        db=db,
        commit=db.commit,
    )
    logger.info(
        "Bulk import: enqueued durable file jobs",
        extra=core_logger.context(user_id=user_id, file_count=len(file_paths)),
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
    payload = ingestion_events.BulkImportFilePayload.model_validate(event.payload)
    # The file path arrives in the (durable, replayable) event payload; re-verify
    # it still resolves under the trusted bulk-import directory before touching the
    # file, so a corrupted or forged job cannot read or move an arbitrary path.
    file_path = str(core_file_uploads.ensure_within(payload.file_path, core_config.FILES_BULK_IMPORT_DIR))
    try:
        with core_database.SessionLocal() as db:
            bulk_entry.store_bulk_import_file(payload.user_id, file_path, payload.import_initiated_time, db)
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
        core_file_uploads.move_within(
            file_path,
            error_dir,
            filename=os.path.basename(file_path),
            src_base_dir=core_config.FILES_BULK_IMPORT_DIR,
        )
        logger.error(
            f"Bulk import: dead-lettered file {file_path} moved to {error_dir}", extra=core_logger.context(console=True)
        )
    except OSError:
        logger.error(
            f"Bulk import: failed to move dead-lettered file {file_path} to the import-error directory",
            extra=core_logger.context(console=True),
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
