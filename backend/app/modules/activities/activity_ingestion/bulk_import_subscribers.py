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
from collections.abc import Callable

from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import infra.event_versioning as platform_event_versioning
import infra.publisher as platform_publisher
import modules.activities.activity_ingestion.bulk_entry as bulk_entry
import modules.activities.activity_ingestion.crud as ingestion_jobs_crud
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.staging as staging
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry

logger = core_logger.get_logger(__name__)

# Stable durable-subscriber id (independent of module path) so job history and
# dedup survive refactors.
BULK_IMPORT_FILE_SUBSCRIBER_ID = "activity_ingestion.bulk_import_file"


def _mark(job_id: str | None, transition: Callable[[str, Session], None]) -> None:
    """Apply a job-state transition, if this file has a handle to report through.

    Args:
        job_id: The ``activity_ingestion_jobs`` row, or ``None`` for a v2 event
            staged before per-file handles existed.
        transition: The CRUD transition to run on its own session.

    Returns:
        None.
    """
    if job_id is None:
        return
    with core_database.SessionLocal() as db:
        transition(job_id, db)


def publish_bulk_import_files(
    queued_files: list[tuple[str, str]],
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
        queued_files: ``(ingestion job id, absolute file path)`` per queued file.
            The job row is what the caller polls; it is created by
            :mod:`~modules.activities.activity_ingestion.bulk_import_service` on
            the same session, so it commits with the outbox rows.
        user_id: ID of the user performing the import.
        import_initiated_time: ISO timestamp of when the bulk import was initiated.
        db: The request's database session (the outbox rows are staged on it).

    Returns:
        None.

    Raises:
        Exception: Propagated from the outbox staging so the caller can fail the
            request instead of reporting a false success.
    """
    # Staged here, in the request thread, because this is the only place
    # guaranteed to see the dropped file. A worker that claims the job may be on
    # another node entirely.
    staged: list[tuple[str, str, str]] = []
    try:
        for job_id, file_path in queued_files:
            staged.append((job_id, staging.stage_file(user_id, file_path), file_path))

        platform_publisher.publish_many_committing(
            ingestion_events.ACTIVITY_BULK_IMPORT_FILE,
            [
                {
                    "job_id": job_id,
                    "storage_key": key,
                    "filename": os.path.basename(file_path),
                    "user_id": user_id,
                    "import_initiated_time": import_initiated_time,
                }
                for job_id, key, file_path in staged
            ],
            source="api:bulk_import",
            db=db,
            commit=db.commit,
            schema_version=ingestion_events.BulkImportFilePayload.SCHEMA_VERSION,
        )
    except Exception:
        # Nothing will import these blobs, and the caller gets a 500. Drop them
        # and leave the dropped files alone so the user can simply retry.
        staging.unstage([key for _, key, _ in staged])
        raise

    # Only now are the jobs durable, so consuming the originals is safe.
    staging.settle([(key, file_path) for _, key, file_path in staged], user_id)
    logger.info(
        "Bulk import: enqueued durable file jobs",
        extra=core_logger.context(user_id=user_id, file_count=len(queued_files)),
    )


def process_bulk_import_file_for_event(event: Event) -> None:
    """Durable handler: import one staged bulk-import file; raises so the runner retries.

    The durable-job handler for ``activity.bulk_import_file``: any error
    propagates so the runner retries with backoff and eventually dead-letters the
    job. On the final attempt the staged blob is moved to the import-error area
    first, so a dead-lettered file still leaves a human trail — but only after
    the retries are exhausted, not on the first error.

    The caller's ``activity_ingestion_jobs`` row is moved along with the work, so
    the handle returned by ``POST /activities/bulk-import`` reports the same
    outcome the runner reached. Only the last attempt records a failure: an
    earlier one is still going to be retried, and reporting it as terminal would
    tell the owner the file failed while the import is still in progress.

    Args:
        event: The ``activity.bulk_import_file`` event (payload
            ``{"job_id": str | None, "storage_key": str, "filename": str,
            "user_id": int, "import_initiated_time": str}``).

    Returns:
        None.
    """
    payload = platform_event_versioning.parse_payload(ingestion_events.BulkImportFilePayload, event)
    _mark(payload.job_id, ingestion_jobs_crud.mark_processing)
    try:
        with staging.materialized(payload.storage_key, payload.filename) as file_path:
            if file_path is None:
                # Already imported and discarded: a duplicate delivery, not a
                # failure. Raising would retry until the job dead-lettered.
                logger.info(
                    "Bulk import: skipping a job whose file is no longer staged",
                    extra=core_logger.context(
                        user_id=payload.user_id, file=payload.filename, storage_key=payload.storage_key
                    ),
                )
                return
            with core_database.SessionLocal() as db:
                activities = bulk_entry.store_bulk_import_file(
                    payload.user_id, file_path, payload.import_initiated_time, db
                )
        staging.discard(payload.storage_key)
        _mark(
            payload.job_id,
            lambda job_id, db: ingestion_jobs_crud.mark_completed(
                job_id, [activity.id for activity in activities or [] if activity.id is not None], db
            ),
        )
        logger.debug(
            "Imported a bulk-import file",
            extra=core_logger.context(user_id=payload.user_id, file=payload.filename),
        )
    except Exception as err:
        # ``retry_count`` is the (claim-incremented) attempt number; when it has
        # reached the ceiling this failure dead-letters the job.
        if event.retry_count >= core_config.settings.JOBS_MAX_ATTEMPTS:
            staging.move_to_errors(payload.storage_key, payload.user_id, payload.filename)
            _mark(
                payload.job_id,
                lambda job_id, db: ingestion_jobs_crud.mark_failed(
                    job_id, activity_ingestion_schema.IngestionJobErrorCode.PROCESSING_FAILED, db
                ),
            )
        else:
            logger.warning(
                "Bulk-import file failed; the job will be retried",
                exc_info=err,
                extra=core_logger.context(
                    user_id=payload.user_id,
                    file=payload.filename,
                    attempt=event.retry_count,
                    max_attempts=core_config.settings.JOBS_MAX_ATTEMPTS,
                ),
            )
        raise


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
