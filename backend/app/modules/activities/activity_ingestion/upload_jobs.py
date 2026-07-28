"""Accepting and running activity upload jobs.

The seam between the two halves of :mod:`upload_entry`. :func:`accept_upload`
runs in the request and returns a handle; :func:`run_upload_job` is the job
body, and is deliberately identical whichever executor calls it — the durable
worker when ``JOBS_ENABLED``, the in-process pool otherwise. The client contract
does not change with the deployment.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity_ingestion.background as activity_ingestion_background
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.upload_crud as upload_crud
import modules.activities.activity_ingestion.upload_entry as upload_entry
from infra import publisher as platform_publisher

logger = core_logger.get_logger(__name__)

# Failure classes the owner can act on, mapped to a stable code. Anything not
# listed collapses to PROCESSING_FAILED: the exception text can carry filesystem
# paths and parser internals, so only this closed set ever reaches a client.
_ERROR_CODES: dict[type[Exception], activity_ingestion_schema.UploadJobErrorCode] = {
    core_exceptions.UnsupportedFormatError: activity_ingestion_schema.UploadJobErrorCode.UNSUPPORTED_FORMAT,
    core_exceptions.InvalidInputError: activity_ingestion_schema.UploadJobErrorCode.INVALID_FILE,
}


def _error_code_for(error: Exception) -> activity_ingestion_schema.UploadJobErrorCode:
    """Map an exception to the sanitized code shown to the uploader.

    Args:
        error: The failure raised by the import.

    Returns:
        The matching error code, or ``PROCESSING_FAILED``.
    """
    for error_type, code in _ERROR_CODES.items():
        if isinstance(error, error_type):
            return code
    return activity_ingestion_schema.UploadJobErrorCode.PROCESSING_FAILED


def accept_upload(
    token_user_id: int,
    file: UploadFile,
    db: Session,
) -> activity_ingestion_schema.ActivityUploadJob:
    """Stage an uploaded file and queue it for background import.

    The staging write happens before the row is created so a rejected file never
    leaves a job behind. The row and the event are then committed together, so a
    crash between them cannot produce a job nobody will ever run.

    Args:
        token_user_id: Authenticated user ID.
        file: Incoming FastAPI UploadFile.
        db: Database session.

    Returns:
        The accepted upload job, in the pending state.

    Raises:
        InvalidInputError: When the filename is missing.
        UnsupportedFormatError: When the extension is not a supported format.
        HTTPException: When the shared upload validators reject the payload.
    """
    staged_key = upload_entry.stage_uploaded_activity_file(file)
    job_id = str(uuid.uuid4())

    try:
        upload_crud.create_upload_job(
            job_id,
            token_user_id,
            # ``file.filename`` is non-None here: staging rejects a missing one.
            str(file.filename),
            staged_key,
            db,
            commit=False,
        )
        if core_config.settings.JOBS_ENABLED:
            # Staged in the transactional outbox on this session and committed
            # with the job row, then relayed into a retryable processing_jobs
            # row. A staging failure propagates, so the caller gets a 500 rather
            # than a 202 for an upload that was never queued.
            platform_publisher.publish_committing(
                ingestion_events.ACTIVITY_FILE_UPLOADED,
                {"job_id": job_id},
                source="api:upload",
                db=db,
                commit=db.commit,
                metadata={"user_id": token_user_id},
            )
        else:
            db.commit()
    except Exception:
        # The row is gone (or never committed), so nothing will consume the
        # staged bytes.
        upload_entry.discard_staged_upload(staged_key)
        raise

    if not core_config.settings.JOBS_ENABLED:
        # No durable worker to drain the queue; fall back to the background pool
        # so the parse still leaves the request threadpool alone. In-flight work
        # is lost on restart, which is exactly the reliability gap durable jobs
        # close.
        activity_ingestion_background.submit_upload(job_id)

    logger.info(
        "Activity upload accepted for background import",
        extra=core_logger.context(user_id=token_user_id, job_id=job_id),
    )
    return upload_crud.get_upload_job(job_id, token_user_id, db) or _pending_view(job_id, str(file.filename))


def _pending_view(job_id: str, filename: str) -> activity_ingestion_schema.ActivityUploadJob:
    """Build the pending response when the row cannot be re-read.

    Only reachable if the job completed and was pruned between the commit and
    the read-back; returning the handle the caller needs is better than a 500.

    Args:
        job_id: The accepted job identifier.
        filename: Original client filename.

    Returns:
        A pending view of the job.
    """
    now = datetime.now(UTC)
    return activity_ingestion_schema.ActivityUploadJob(
        id=job_id,
        filename=filename,
        status=activity_ingestion_schema.UploadJobStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


def run_upload_job(job_id: str) -> None:
    """Import a staged upload, recording the outcome on the job row.

    The job body for both executors. Opens its own session because neither the
    durable worker nor the background pool has a request-scoped one.

    Failure handling splits on whether another attempt could plausibly succeed.
    A rejected file (bad format, unreadable payload) fails identically every
    time, so it is recorded as terminal immediately rather than burning five
    attempts before telling the user. A server-side fault is left to propagate
    so the durable runner retries it with backoff, and the staged blob is kept
    so that retry has something to read \u2014 unless nothing will retry, which is
    the case when durable jobs are off and the fallback pool runs each job once.

    Args:
        job_id: The ``activity_upload_jobs`` row to process.

    Returns:
        None.

    Raises:
        Exception: Whatever the import raised, so the caller can retry.
    """
    with core_database.SessionLocal() as db:
        work_item = upload_crud.get_job_work_item(job_id, db)
        if work_item is None:
            # Already consumed — a retry after the import succeeded, or a job
            # whose row was pruned. Nothing to do, and re-running would be wrong.
            logger.info(
                "Skipping an upload job with no staged upload",
                extra=core_logger.context(job_id=job_id),
            )
            return
        user_id, staged_key = work_item
        upload_crud.mark_processing(job_id, db)

    with core_database.SessionLocal() as db:
        try:
            created = upload_entry.process_staged_upload(user_id, staged_key, db)
        except (
            core_exceptions.UnsupportedFormatError,
            core_exceptions.InvalidInputError,
            HTTPException,
        ) as err:
            # The file itself is the problem, so every retry reaches the same
            # verdict: record it now and drop the blob nothing will read again.
            fail_upload_job(job_id, _error_code_for(err), staged_key)
            raise
        except Exception:
            # Server-side, possibly transient. Keep the blob for the retry, and
            # only give up here when there is no retry to wait for.
            if not core_config.settings.JOBS_ENABLED:
                fail_upload_job(
                    job_id,
                    activity_ingestion_schema.UploadJobErrorCode.PROCESSING_FAILED,
                    staged_key,
                )
            raise

        # ``Activity.id`` is typed optional on the read model even though a
        # persisted activity always has one, so filter rather than assert: an
        # id-less entry would only mean the client cannot refresh that one row.
        activity_ids = [activity.id for activity in created or [] if activity.id is not None]
        if not activity_ids:
            upload_crud.mark_failed(
                job_id,
                activity_ingestion_schema.UploadJobErrorCode.NO_ACTIVITIES_FOUND,
                db,
            )
            logger.info(
                "Upload job produced no activities",
                extra=core_logger.context(user_id=user_id, job_id=job_id),
            )
            return
        upload_crud.mark_completed(job_id, activity_ids, db)
        logger.info(
            "Upload job imported activities",
            extra=core_logger.context(user_id=user_id, job_id=job_id, activity_count=len(activity_ids)),
        )


def fail_upload_job(
    job_id: str,
    error_code: activity_ingestion_schema.UploadJobErrorCode,
    staged_key: str | None = None,
) -> None:
    """Record a terminal failure on a job and drop its staged upload.

    Separate session because the caller's may be in a failed transaction.

    Args:
        job_id: The job identifier.
        error_code: Sanitized failure reason.
        staged_key: Storage key to discard, when the caller already knows it.
            Omitted by the dead-letter path, which reads it from the row.

    Returns:
        None.
    """
    try:
        with core_database.SessionLocal() as db:
            if staged_key is None:
                work_item = upload_crud.get_job_work_item(job_id, db)
                staged_key = work_item[1] if work_item else None
            upload_crud.mark_failed(job_id, error_code, db)
    except Exception as err:
        # Never mask the original failure with a bookkeeping one.
        logger.error(
            "Could not mark an upload job failed",
            exc_info=err,
            extra=core_logger.context(job_id=job_id),
        )

    # After the row is terminal, so a crash in between leaves a readable blob
    # rather than a job pointing at bytes that are gone.
    if staged_key is not None:
        upload_entry.discard_staged_upload(staged_key)


# Single-runner lock name: the deletes are idempotent, but the lock keeps the
# work from being duplicated across replicas.
_PRUNE_LOCK_NAME = "activity_upload_jobs_prune"


def prune_expired_upload_jobs() -> None:
    """Prune finished upload jobs older than the durable-job retention window.

    Mirrors :func:`infra.retention.prune_expired_records`: same schedule, same
    ``JOBS_RETENTION_DAYS`` window, same platform lock so only one replica does
    the work. It cannot live in that module because ``activity_upload_jobs`` is
    a domain table and the substrate must not import a domain module.

    The window is shared rather than given its own setting because these rows
    are job history with the same lifecycle as ``processing_jobs``: an operator
    asking to keep job history for N days means all of it.

    Only terminal rows are removed. Pending and processing jobs are in-flight
    work whose owner is still polling, and deleting one would strand both the
    poller and the staged blob.

    Returns:
        None.
    """
    retention_days = core_config.settings.JOBS_RETENTION_DAYS
    if retention_days <= 0:
        return

    platform = platform_runtime.get_active_platform()
    with platform.lock.try_acquire(_PRUNE_LOCK_NAME) as acquired:
        if not acquired:
            logger.debug("Upload job prune: another replica holds the lock; skipping")
            return
        cutoff = platform.clock.now() - timedelta(days=retention_days)
        with core_database.SessionLocal() as db:
            deleted = upload_crud.delete_jobs_before(cutoff, db)

    if deleted:
        logger.info(f"Upload job prune: deleted {deleted} finished upload job row(s)")
    else:
        logger.debug("Upload job prune: nothing to delete")
