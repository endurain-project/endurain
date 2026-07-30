"""Accepting and running activity ingestion jobs.

Two ways activities enter the system on a user's request — an uploaded file and
a provider refresh — and both work the same way: the route accepts, returns a
handle, and the work runs on a background worker. ``accept_*`` runs in the
request; ``run_*_job`` is the job body, deliberately identical whichever
executor calls it (the durable worker when ``JOBS_ENABLED``, the in-process pool
otherwise), so the client contract does not change with the deployment.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity_ingestion.background as activity_ingestion_background
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.ingestion_jobs_crud as ingestion_jobs_crud
import modules.activities.activity_ingestion.refresh_entry as refresh_entry
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.upload_entry as upload_entry
from infra import publisher as platform_publisher

logger = core_logger.get_logger(__name__)

# Failure classes the owner can act on, mapped to a stable code. Anything not
# listed collapses to PROCESSING_FAILED: the exception text can carry filesystem
# paths and parser internals, so only this closed set ever reaches a client.
_ERROR_CODES: dict[type[Exception], activity_ingestion_schema.IngestionJobErrorCode] = {
    core_exceptions.UnsupportedFormatError: activity_ingestion_schema.IngestionJobErrorCode.UNSUPPORTED_FORMAT,
    core_exceptions.InvalidInputError: activity_ingestion_schema.IngestionJobErrorCode.INVALID_FILE,
}


def _error_code_for(error: Exception) -> activity_ingestion_schema.IngestionJobErrorCode:
    """Map an exception to the sanitized code shown to the uploader.

    Args:
        error: The failure raised by the import.

    Returns:
        The matching error code, or ``PROCESSING_FAILED``.
    """
    for error_type, code in _ERROR_CODES.items():
        if isinstance(error, error_type):
            return code
    return activity_ingestion_schema.IngestionJobErrorCode.PROCESSING_FAILED


def accept_upload(
    token_user_id: int,
    file: UploadFile,
    db: Session,
    *,
    idempotency_key: str | None = None,
) -> activity_ingestion_schema.ActivityIngestionJob:
    """Stage an uploaded file and queue it for background import.

    The staging write happens before the row is created so a rejected file never
    leaves a job behind. The row and the event are then committed together, so a
    crash between them cannot produce a job nobody will ever run.

    When the caller supplies an ``Idempotency-Key``, a replay returns the
    original job instead of importing the file twice. The activity-level
    content dedup would already stop a duplicate *activity*, but only after the
    file has been stored and parsed — the key short-circuits before either, so a
    client retrying on a flaky connection does not pay for a second 200 MiB
    storage write and a second parse.

    Reusing a key for *different* content is rejected rather than answered with
    the first job: silently returning it would tell the client the second file
    imported when it never will.

    Args:
        token_user_id: Authenticated user ID.
        file: Incoming FastAPI UploadFile.
        db: Database session.
        idempotency_key: Client-supplied key identifying this request.

    Returns:
        The accepted upload job, in the pending state — or the job the same key
        was accepted with previously.

    Raises:
        InvalidInputError: When the filename is missing.
        UnsupportedFormatError: When the extension is not a supported format.
        ConflictError: When the key was already used for different content.
        HTTPException: When the shared upload validators reject the payload.
    """
    received = upload_entry.receive_upload(file, fingerprint=idempotency_key is not None)

    if idempotency_key:
        prior = ingestion_jobs_crud.get_job_for_idempotency(
            idempotency_key, token_user_id, activity_ingestion_schema.IngestionJobKind.UPLOAD, db
        )
        if prior is not None:
            replayed, fingerprint = prior
            upload_entry.discard_received_upload(received)
            if fingerprint != received.fingerprint:
                raise core_exceptions.ConflictError("This Idempotency-Key was already used for a different file")
            logger.info(
                "Replayed activity upload returned the original job",
                extra=core_logger.context(user_id=token_user_id, job_id=replayed.id),
            )
            return replayed

    staged_key = upload_entry.store_received_upload(received)
    job_id = str(uuid.uuid4())

    try:
        ingestion_jobs_crud.create_ingestion_job(
            job_id,
            token_user_id,
            activity_ingestion_schema.IngestionJobKind.UPLOAD,
            db,
            # ``file.filename`` is non-None here: staging rejects a missing one.
            filename=str(file.filename),
            staged_key=staged_key,
            idempotency_key=idempotency_key,
            request_fingerprint=received.fingerprint,
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
    except IntegrityError:
        # Two requests carrying the same key raced past the check above. The
        # constraint is what actually decides; the loser reports the winner's job.
        upload_entry.discard_staged_upload(staged_key)
        db.rollback()
        prior = (
            ingestion_jobs_crud.get_job_for_idempotency(
                idempotency_key, token_user_id, activity_ingestion_schema.IngestionJobKind.UPLOAD, db
            )
            if idempotency_key
            else None
        )
        if prior is None:
            raise
        replayed, fingerprint = prior
        if fingerprint != received.fingerprint:
            raise core_exceptions.ConflictError("This Idempotency-Key was already used for a different file") from None
        return replayed
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
    return ingestion_jobs_crud.get_ingestion_job(job_id, token_user_id, db) or _pending_view(
        job_id, activity_ingestion_schema.IngestionJobKind.UPLOAD, str(file.filename)
    )


def _pending_view(
    job_id: str,
    kind: activity_ingestion_schema.IngestionJobKind,
    filename: str | None = None,
) -> activity_ingestion_schema.ActivityIngestionJob:
    """Build the pending response when the row cannot be re-read.

    Only reachable if the job completed and was pruned between the commit and
    the read-back; returning the handle the caller needs is better than a 500.

    Args:
        job_id: The accepted job identifier.
        kind: Whether this job imports an upload or syncs from providers.
        filename: Original client filename, for an upload.

    Returns:
        A pending view of the job.
    """
    now = datetime.now(UTC)
    return activity_ingestion_schema.ActivityIngestionJob(
        id=job_id,
        kind=kind,
        filename=filename,
        status=activity_ingestion_schema.IngestionJobStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


def accept_refresh(
    token_user_id: int,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJob:
    """Queue a provider refresh for background execution.

    The route used to be the one ``async def`` in activities, awaiting the
    Strava and Garmin clients directly. That made every synchronous call on
    those paths — the provider integration lookups, the per-activity dedup
    reads — run on the event loop, where they stall every other request in the
    process rather than occupying one worker thread. Moving the work to a job
    removes the question entirely: nothing on this path touches the loop.

    Args:
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        The accepted refresh job, in the pending state.
    """
    job_id = str(uuid.uuid4())

    ingestion_jobs_crud.create_ingestion_job(
        job_id,
        token_user_id,
        activity_ingestion_schema.IngestionJobKind.REFRESH,
        db,
        commit=False,
    )
    if core_config.settings.JOBS_ENABLED:
        platform_publisher.publish_committing(
            ingestion_events.ACTIVITY_REFRESH_REQUESTED,
            {"job_id": job_id},
            source="api:refresh",
            db=db,
            commit=db.commit,
            metadata={"user_id": token_user_id},
        )
    else:
        db.commit()
        activity_ingestion_background.submit_refresh(job_id)

    logger.info(
        "Provider refresh accepted for background sync",
        extra=core_logger.context(user_id=token_user_id, job_id=job_id),
    )
    return ingestion_jobs_crud.get_ingestion_job(job_id, token_user_id, db) or _pending_view(
        job_id, activity_ingestion_schema.IngestionJobKind.REFRESH
    )


def run_refresh_job(job_id: str) -> None:
    """Pull the last 24h from the linked providers, recording the outcome.

    The job body for both executors. The provider helpers are still ``async``
    (they offload their blocking HTTP clients with ``asyncio.to_thread``), so
    they are driven here by :func:`asyncio.run` on a loop private to this worker
    thread. That is what keeps their synchronous database calls off the main
    loop — the whole point of moving this off the request.

    Args:
        job_id: The ``activity_ingestion_jobs`` row to process.

    Returns:
        None.

    Raises:
        Exception: Whatever the provider sync raised, so the caller can retry.
    """
    with core_database.SessionLocal() as db:
        owner = ingestion_jobs_crud.get_job_owner(job_id, db)
        if owner is None:
            logger.info("Skipping an unknown refresh job", extra=core_logger.context(job_id=job_id))
            return
        ingestion_jobs_crud.mark_processing(job_id, db)

    with core_database.SessionLocal() as db:
        try:
            activities = asyncio.run(refresh_entry.sync_linked_providers(owner, db))
        except Exception:
            if not core_config.settings.JOBS_ENABLED:
                # Nothing will retry, so leave the caller a terminal state
                # instead of a job stuck at "processing".
                fail_ingestion_job(job_id, activity_ingestion_schema.IngestionJobErrorCode.PROVIDER_UNAVAILABLE)
            raise

        activity_ids = [activity.id for activity in activities if activity.id is not None]
        ingestion_jobs_crud.mark_completed(job_id, activity_ids, db)
        logger.info(
            "Refresh job synced provider activities",
            extra=core_logger.context(user_id=owner, job_id=job_id, activity_count=len(activity_ids)),
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
        work_item = ingestion_jobs_crud.get_job_work_item(job_id, db)
        if work_item is None:
            # Already consumed — a retry after the import succeeded, or a job
            # whose row was pruned. Nothing to do, and re-running would be wrong.
            logger.info(
                "Skipping an upload job with no staged upload",
                extra=core_logger.context(job_id=job_id),
            )
            return
        user_id, staged_key = work_item
        ingestion_jobs_crud.mark_processing(job_id, db)

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
            fail_ingestion_job(job_id, _error_code_for(err), staged_key)
            raise
        except Exception:
            # Server-side, possibly transient. Keep the blob for the retry, and
            # only give up here when there is no retry to wait for.
            if not core_config.settings.JOBS_ENABLED:
                fail_ingestion_job(
                    job_id,
                    activity_ingestion_schema.IngestionJobErrorCode.PROCESSING_FAILED,
                    staged_key,
                )
            raise

        # ``Activity.id`` is typed optional on the read model even though a
        # persisted activity always has one, so filter rather than assert: an
        # id-less entry would only mean the client cannot refresh that one row.
        activity_ids = [activity.id for activity in created or [] if activity.id is not None]
        if not activity_ids:
            ingestion_jobs_crud.mark_failed(
                job_id,
                activity_ingestion_schema.IngestionJobErrorCode.NO_ACTIVITIES_FOUND,
                db,
            )
            logger.info(
                "Upload job produced no activities",
                extra=core_logger.context(user_id=user_id, job_id=job_id),
            )
            return
        ingestion_jobs_crud.mark_completed(job_id, activity_ids, db)
        logger.info(
            "Upload job imported activities",
            extra=core_logger.context(user_id=user_id, job_id=job_id, activity_count=len(activity_ids)),
        )


def fail_ingestion_job(
    job_id: str,
    error_code: activity_ingestion_schema.IngestionJobErrorCode,
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
                work_item = ingestion_jobs_crud.get_job_work_item(job_id, db)
                staged_key = work_item[1] if work_item else None
            ingestion_jobs_crud.mark_failed(job_id, error_code, db)
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
_PRUNE_LOCK_NAME = "activity_ingestion_jobs_prune"


def prune_expired_ingestion_jobs() -> None:
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
            logger.debug("Ingestion job prune: another replica holds the lock; skipping")
            return
        cutoff = platform.clock.now() - timedelta(days=retention_days)
        with core_database.SessionLocal() as db:
            deleted = ingestion_jobs_crud.delete_jobs_before(cutoff, db)

    if deleted:
        logger.info(f"Ingestion job prune: deleted {deleted} finished upload job row(s)")
    else:
        logger.debug("Ingestion job prune: nothing to delete")
