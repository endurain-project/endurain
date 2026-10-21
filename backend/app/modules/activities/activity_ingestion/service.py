"""Accepting and running activity ingestion jobs.

Activities enter on a user's request three ways — an uploaded file, a provider
refresh and a bulk import (:mod:`bulk_import_service`) — and all work the same
way: the route accepts, returns a handle, and the work runs on a background
worker. ``accept_*`` runs in the request; ``run_*_job`` is the job body,
deliberately identical whichever executor calls it (the durable worker when
``JOBS_ENABLED``, the in-process pool otherwise), so the client contract does not
change with the deployment.

This service owns the transaction for every job row: the entry points hand it
the storage provider and it stages, publishes and commits.

Nothing here is transport-aware: it takes a user id and a session, returns the
job handles it queued, and raises :mod:`core.exceptions` so the same call works
from a future CLI or scheduled trigger without constructing an HTTP response.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import batched

import jasil.providers as platform_providers
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.crud as activity_ingestion_crud
import modules.activities.activity_ingestion.dispatch_service as activity_ingestion_dispatch_service
import modules.activities.activity_ingestion.event_publishers as activity_ingestion_event_publishers
import modules.activities.activity_ingestion.provider_registry as activity_ingestion_provider_registry
import modules.activities.activity_ingestion.refresh_entry_service as activity_ingestion_refresh_entry_service
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.upload_entry_service as activity_ingestion_upload_entry_service

logger = core_logger.get_logger(__name__)

# Failure classes the owner can act on, mapped to a stable code. Anything not
# listed collapses to PROCESSING_FAILED: the exception text can carry filesystem
# paths and parser internals, so only this closed set ever reaches a client.
_ERROR_CODES: dict[type[Exception], activity_ingestion_constants.IngestionJobErrorCode] = {
    core_exceptions.UnsupportedFormatError: activity_ingestion_constants.IngestionJobErrorCode.UNSUPPORTED_FORMAT,
    core_exceptions.InvalidInputError: activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE,
}


def error_code_for(error: Exception) -> activity_ingestion_constants.IngestionJobErrorCode:
    """Map an exception to the sanitized code shown to the uploader.

    Args:
        error: The failure raised by the import.

    Returns:
        The matching error code, or ``PROCESSING_FAILED``.
    """
    for error_type, code in _ERROR_CODES.items():
        if isinstance(error, error_type):
            return code
    return activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED


def _created_activities_are_gone(job: activity_ingestion_schema.ActivityIngestionJobRead, db: Session) -> bool:
    """Whether a finished import's result no longer exists.

    A key stands for "this upload was done". Once every activity the import
    created has been deleted, that is no longer true, and replaying the job would
    report a success that left nothing behind.

    Args:
        job: The job the key was accepted with.
        db: Database session.

    Returns:
        True when the job completed having created activities and none remain.
    """
    if job.status != activity_ingestion_constants.IngestionJobStatus.COMPLETED or not job.activity_ids:
        return False
    return not activity_integration.filter_existing_activity_ids(job.activity_ids, db)


def accept_upload(
    token_user_id: int,
    filename: str | None,
    save_upload: activity_ingestion_upload_entry_service.UploadSaver,
    storage: platform_providers.StorageProvider,
    db: Session,
    *,
    idempotency_key: str | None = None,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
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

    A key is released only when its job completed, recorded the activities it
    created and every one of them has been deleted, so the same file can be
    uploaded again under it instead of replaying a success that left nothing
    behind. A job that failed, is still running or recorded no activities keeps
    its key.

    Reusing a key for *different* content is rejected, before any release, rather
    than answered with the first job: silently returning it would tell the client the second file
    imported when it never will.

    Args:
        token_user_id: Authenticated user ID.
        filename: The client-supplied filename.
        save_upload: Validates the request's upload and streams it to disk.
        storage: The blob-storage provider the upload is staged in.
        db: Database session.
        idempotency_key: Client-supplied key identifying this request.

    Returns:
        The accepted upload job, in the pending state — or the job the same key
        was accepted with previously.

    Raises:
        InvalidInputError: When the filename is missing.
        UnsupportedFormatError: When the extension is not a supported format.
        ConflictError: When the key was already used for different content.
        DomainError: When the shared upload validators reject the payload.
    """
    received = activity_ingestion_upload_entry_service.receive_upload(
        filename, save_upload, fingerprint=idempotency_key is not None
    )

    if idempotency_key:
        try:
            prior = activity_ingestion_crud.get_job_for_idempotency(
                idempotency_key, token_user_id, activity_ingestion_constants.IngestionJobKind.UPLOAD, db
            )
            if prior is not None:
                if prior[1] != received.fingerprint:
                    raise core_exceptions.ConflictError("This Idempotency-Key was already used for a different file")
                if _created_activities_are_gone(prior[0], db):
                    # Staged here and committed with the new job below, so the key
                    # is never left free without a job holding it.
                    activity_ingestion_crud.release_idempotency_key(prior[0].id, db)
                    logger.info(
                        "Released the idempotency key of an upload whose activities were deleted",
                        extra=core_logger.context(user_id=token_user_id, job_id=prior[0].id),
                    )
                    prior = None
        except Exception:
            # The upload is on local disk and nothing else will remove it.
            activity_ingestion_upload_entry_service.discard_received_upload(received)
            raise
        if prior is not None:
            replayed = prior[0]
            activity_ingestion_upload_entry_service.discard_received_upload(received)
            logger.info(
                "Replayed activity upload returned the original job",
                extra=core_logger.context(user_id=token_user_id, job_id=replayed.id),
            )
            return replayed

    staged_key = activity_ingestion_upload_entry_service.store_received_upload(received, storage)
    job_id = str(uuid.uuid4())

    try:
        activity_ingestion_crud.create_ingestion_job(
            job_id,
            token_user_id,
            activity_ingestion_constants.IngestionJobKind.UPLOAD,
            db,
            # ``filename`` is non-None here: ``receive_upload`` rejects a missing one.
            filename=str(filename),
            staged_key=staged_key,
            idempotency_key=idempotency_key,
            request_fingerprint=received.fingerprint,
        )
        # Durable profile: staged in the transactional outbox on this session
        # and committed with the job row, then relayed into a retryable
        # processing_jobs row. A staging failure propagates, so the caller gets
        # a 500 rather than a 202 for an upload that was never queued.
        activity_ingestion_dispatch_service.commit_or_publish(
            db,
            publish=lambda commit: activity_ingestion_event_publishers.publish_file_uploaded(
                job_id, token_user_id, db, commit=commit
            ),
        )
    except IntegrityError:
        # Two requests carrying the same key raced past the check above. The
        # constraint is what actually decides; the loser reports the winner's job.
        activity_ingestion_upload_entry_service.discard_staged_upload(staged_key, storage)
        db.rollback()
        prior = (
            activity_ingestion_crud.get_job_for_idempotency(
                idempotency_key, token_user_id, activity_ingestion_constants.IngestionJobKind.UPLOAD, db
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
        activity_ingestion_upload_entry_service.discard_staged_upload(staged_key, storage)
        raise

    # No durable worker drains the queue on the local profile, so the parse runs
    # on the background pool and leaves the request threadpool alone. In-flight
    # work is lost on restart, which is the reliability gap durable jobs close.
    activity_ingestion_dispatch_service.run_in_background(run_upload_job, job_id, storage)

    logger.info(
        "Activity upload accepted for background import",
        extra=core_logger.context(user_id=token_user_id, job_id=job_id),
    )
    return activity_ingestion_crud.get_ingestion_job(job_id, token_user_id, db) or _pending_view(
        job_id, activity_ingestion_constants.IngestionJobKind.UPLOAD, str(filename)
    )


def _pending_view(
    job_id: str,
    kind: activity_ingestion_constants.IngestionJobKind,
    filename: str | None = None,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
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
    return activity_ingestion_schema.ActivityIngestionJobRead(
        id=job_id,
        kind=kind,
        filename=filename,
        status=activity_ingestion_constants.IngestionJobStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


def get_job(
    job_id: str,
    token_user_id: int,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Return one of the caller's ingestion jobs.

    Args:
        job_id: The job identifier returned by the upload or refresh route.
        token_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The ingestion job.

    Raises:
        NotFoundError: When no such job belongs to the caller. A job owned by
            someone else is reported as missing rather than forbidden, so the
            endpoint does not confirm that an id exists.
    """
    job = activity_ingestion_crud.get_ingestion_job(job_id, token_user_id, db)
    if job is None:
        logger.debug(
            "Ingestion job read resolved to nothing for this caller",
            extra=core_logger.context(job_id=job_id, user_id=token_user_id),
        )
        raise core_exceptions.NotFoundError("Upload job not found")
    return job


def accept_refresh(
    token_user_id: int,
    storage: platform_providers.StorageProvider,
    db: Session,
    *,
    provider: str | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a provider refresh for background execution.

    The provider fetch runs in the job, never on the request path.

    Args:
        token_user_id: Authenticated user ID.
        storage: The blob-storage provider handed to the in-process fallback.
        db: Database session.
        provider: Sync only this provider; ``None`` syncs every linked one.
        window_start: Start of the window to fetch; ``None`` means the last day.
        window_end: End of the window to fetch; ``None`` means now.

    Returns:
        The accepted refresh job, in the pending state.
    """
    job_id = str(uuid.uuid4())

    activity_ingestion_crud.create_ingestion_job(
        job_id,
        token_user_id,
        activity_ingestion_constants.IngestionJobKind.REFRESH,
        db,
        provider=provider,
        window_start=window_start,
        window_end=window_end,
    )
    activity_ingestion_dispatch_service.commit_or_publish(
        db,
        publish=lambda commit: activity_ingestion_event_publishers.publish_refresh_requested(
            job_id, token_user_id, db, commit=commit
        ),
    )
    activity_ingestion_dispatch_service.run_in_background(run_refresh_job, job_id, storage)

    logger.info(
        "Provider refresh accepted for background sync",
        extra=core_logger.context(user_id=token_user_id, job_id=job_id, provider=provider),
    )
    return activity_ingestion_crud.get_ingestion_job(job_id, token_user_id, db) or _pending_view(
        job_id, activity_ingestion_constants.IngestionJobKind.REFRESH
    )


def run_refresh_job(job_id: str, storage: platform_providers.StorageProvider) -> None:
    """Pull the job's window from the linked providers, recording the outcome.

    The job body for both executors. It is synchronous and runs on a worker
    thread; the providers open their own short sessions, so none is held here
    while a provider is being called. The row is read, marked processing and
    committed in one short session, and the outcome is recorded in another.

    Args:
        job_id: The ``activity_ingestion_jobs`` row to process.
        storage: The blob-storage provider, for discarding a staged upload.

    Raises:
        Exception: Whatever the provider sync raised, so the caller can retry.
    """
    with core_database.SessionLocal() as db:
        scope = activity_ingestion_crud.get_refresh_scope(job_id, db)
        if scope is None:
            logger.debug("Skipping an unknown refresh job", extra=core_logger.context(job_id=job_id))
            return
        if not activity_ingestion_crud.mark_processing(
            job_id, db, lease=activity_ingestion_dispatch_service.claim_lease()
        ):
            logger.debug(
                "Skipping a refresh job that already finished or is claimed elsewhere",
                extra=core_logger.context(job_id=job_id),
            )
            return
        db.commit()
    owner, provider, window_start, window_end = scope

    try:
        activities = activity_ingestion_refresh_entry_service.sync_linked_providers(
            owner, window_start, window_end, provider=provider
        )
    except Exception:
        if not activity_ingestion_dispatch_service.worker_retries():
            # Nothing will retry, so leave the caller a terminal state
            # instead of a job stuck at "processing".
            fail_ingestion_job(job_id, activity_ingestion_constants.IngestionJobErrorCode.PROVIDER_UNAVAILABLE, storage)
        else:
            release_ingestion_job(job_id)
        raise

    activity_ids = [activity.id for activity in activities if activity.id is not None]
    with core_database.SessionLocal() as db:
        activity_ingestion_crud.mark_completed(job_id, activity_ids, db)
        db.commit()
    logger.info(
        "Refresh job synced provider activities",
        extra=core_logger.context(user_id=owner, job_id=job_id, activity_count=len(activity_ids)),
    )


# One scheduler replica enqueues the periodic refreshes; the jobs themselves are
# claimed by any worker.
_REFRESH_FANOUT_LOCK_NAME = "activity_ingestion_scheduled_refresh"
_REFRESH_FANOUT_BATCH_SIZE = 200


def enqueue_scheduled_refreshes(
    lock: platform_providers.LockProvider,
    storage: platform_providers.StorageProvider,
) -> int:
    """Queue one refresh job per user who has linked a provider.

    Each user is an independent job, so it is retried, rate-limited and spread across workers on
    its own, and one slow or failing account cannot hold up the rest. Users are
    read a page at a time from each provider's own notion of "linked", and a user
    linked to several providers gets one job, which syncs all of them.

    A user whose previous refresh has not finished is skipped rather than queued
    behind it, so a backed-up queue does not grow by a job per user per run. The
    default window overlaps the next run, so a skipped user loses nothing.

    Args:
        lock: The platform lock provider.
        storage: The blob-storage provider handed to the in-process fallback.

    Returns:
        The number of refresh jobs queued.
    """
    queued = 0
    with lock.try_acquire(_REFRESH_FANOUT_LOCK_NAME) as acquired:
        if not acquired:
            logger.debug("Scheduled refresh: another replica holds the fan-out lock; skipping")
            return 0
        seen: set[int] = set()
        for provider in activity_ingestion_provider_registry.registered():
            after_id = 0
            while True:
                user_ids = provider.linked_user_ids(after_id, _REFRESH_FANOUT_BATCH_SIZE)
                if not user_ids:
                    break
                after_id = user_ids[-1]
                fresh = [user_id for user_id in user_ids if user_id not in seen]
                seen.update(fresh)
                if fresh:
                    queued += _queue_refresh_batch(fresh, storage)

    if queued:
        logger.info("Scheduled refresh queued provider syncs", extra=core_logger.context(queued=queued))
    else:
        logger.debug("Scheduled refresh: nothing to queue")
    return queued


def _queue_refresh_batch(user_ids: list[int], storage: platform_providers.StorageProvider) -> int:
    """Create and dispatch refresh jobs for a batch of users in one transaction.

    Args:
        user_ids: Users to refresh.
        storage: The blob-storage provider handed to the in-process fallback.

    Returns:
        The number of jobs queued (users with a refresh already in flight are
        skipped).
    """
    with core_database.SessionLocal() as db:
        busy = activity_ingestion_crud.get_user_ids_with_active_refresh(user_ids, db)
        jobs = [(str(uuid.uuid4()), user_id) for user_id in user_ids if user_id not in busy]
        if not jobs:
            return 0
        for job_id, user_id in jobs:
            activity_ingestion_crud.create_ingestion_job(
                job_id, user_id, activity_ingestion_constants.IngestionJobKind.REFRESH, db
            )
        activity_ingestion_dispatch_service.commit_or_publish(
            db,
            publish=lambda commit: activity_ingestion_event_publishers.publish_refresh_requests(
                jobs, db, commit=commit
            ),
        )

    for job_id, _user_id in jobs:
        activity_ingestion_dispatch_service.run_in_background(run_refresh_job, job_id, storage)
    logger.debug("Queued a batch of provider refresh jobs", extra=core_logger.context(count=len(jobs)))
    return len(jobs)


def run_upload_job(job_id: str, storage: platform_providers.StorageProvider) -> None:
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
        storage: The blob-storage provider the upload was staged in.

    Raises:
        Exception: Whatever the import raised, so the caller can retry.
    """
    with core_database.SessionLocal() as db:
        work_item = activity_ingestion_crud.get_job_work_item(job_id, db)
        if work_item is None:
            # Already consumed — a retry after the import succeeded, or a job
            # whose row was pruned. Nothing to do, and re-running would be wrong.
            logger.debug(
                "Skipping an upload job with no staged upload",
                extra=core_logger.context(job_id=job_id),
            )
            return
        user_id, staged_key = work_item
        if not activity_ingestion_crud.mark_processing(
            job_id, db, lease=activity_ingestion_dispatch_service.claim_lease()
        ):
            logger.debug(
                "Skipping an upload job that already finished or is claimed elsewhere",
                extra=core_logger.context(job_id=job_id),
            )
            return
        db.commit()

    with core_database.SessionLocal() as db:
        try:
            created = activity_ingestion_upload_entry_service.process_staged_upload(user_id, staged_key, storage, db)
        except (
            core_exceptions.UnsupportedFormatError,
            core_exceptions.InvalidInputError,
            core_exceptions.PayloadTooLargeError,
        ) as err:
            # The file itself is the problem, so every retry reaches the same
            # verdict: record it now and drop the blob nothing will read again.
            # Returning rather than raising keeps the runner from spending an
            # attempt (and a backoff) re-running a job that is already terminal;
            # the outcome the owner reads is on the job row.
            fail_ingestion_job(job_id, error_code_for(err), storage, staged_key)
            logger.warning(
                "Upload job rejected its file",
                extra=core_logger.context(user_id=user_id, job_id=job_id, error_code=error_code_for(err).value),
            )
            return
        except Exception:
            # Server-side, possibly transient. Keep the blob for the retry, and
            # only give up here when there is no retry to wait for.
            if not activity_ingestion_dispatch_service.worker_retries():
                fail_ingestion_job(
                    job_id,
                    activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
                    storage,
                    staged_key,
                )
            else:
                release_ingestion_job(job_id)
            raise

        # ``Activity.id`` is typed optional on the read model even though a
        # persisted activity always has one, so filter rather than assert: an
        # id-less entry would only mean the client cannot refresh that one row.
        activity_ids = [activity.id for activity in created or [] if activity.id is not None]
        if not activity_ids:
            activity_ingestion_crud.mark_failed(
                job_id,
                activity_ingestion_constants.IngestionJobErrorCode.NO_ACTIVITIES_FOUND,
                db,
            )
            db.commit()
            # After the outcome is committed: a crash before this line retries
            # against the blob rather than finding it gone.
            activity_ingestion_upload_entry_service.discard_staged_upload(staged_key, storage)
            logger.info(
                "Upload job produced no activities",
                extra=core_logger.context(user_id=user_id, job_id=job_id),
            )
            return
        activity_ingestion_crud.mark_completed(job_id, activity_ids, db)
        db.commit()
        activity_ingestion_upload_entry_service.discard_staged_upload(staged_key, storage)
        logger.info(
            "Upload job imported activities",
            extra=core_logger.context(user_id=user_id, job_id=job_id, activity_count=len(activity_ids)),
        )


def release_ingestion_job(job_id: str) -> None:
    """Return a failed attempt's job to ``pending`` so the runner's retry can claim it.

    Separate session because the caller's may be in a failed transaction. A
    failure here is logged, not raised: the retry then waits out the lease.

    Args:
        job_id: The job identifier.
    """
    try:
        with core_database.SessionLocal() as db:
            activity_ingestion_crud.release_job(job_id, db)
            db.commit()
    except Exception as err:
        logger.error(
            "Could not release an ingestion job for retry",
            exc_info=err,
            extra=core_logger.context(job_id=job_id),
        )


def fail_ingestion_job(
    job_id: str,
    error_code: activity_ingestion_constants.IngestionJobErrorCode,
    storage: platform_providers.StorageProvider,
    staged_key: str | None = None,
) -> None:
    """Record a terminal failure on a job and drop its staged upload.

    Separate session because the caller's may be in a failed transaction.

    Args:
        job_id: The job identifier.
        error_code: Sanitized failure reason.
        storage: The blob-storage provider the staged upload lives in.
        staged_key: Storage key to discard, when the caller already knows it.
            Omitted by the dead-letter path, which reads it from the row.
    """
    try:
        with core_database.SessionLocal() as db:
            if staged_key is None:
                work_item = activity_ingestion_crud.get_job_work_item(job_id, db)
                staged_key = work_item[1] if work_item else None
            activity_ingestion_crud.mark_failed(job_id, error_code, db)
            db.commit()
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
        activity_ingestion_upload_entry_service.discard_staged_upload(staged_key, storage)


# Single-runner lock name: the deletes are idempotent, but the lock keeps the
# work from being duplicated across replicas.
_PRUNE_LOCK_NAME = "activity_ingestion_jobs_prune"


def prune_expired_ingestion_jobs(
    lock: platform_providers.LockProvider,
    clock: platform_providers.ClockProvider,
) -> None:
    """Prune finished upload jobs older than the durable-job retention window.

    Mirrors :func:`jasil.retention.prune_expired_records`: same schedule, same
    ``JOBS_RETENTION_DAYS`` window, same platform lock so only one replica does
    the work. It cannot live in that module because ``activity_upload_jobs`` is
    a domain table and the substrate must not import a domain module.

    The window is shared rather than given its own setting because these rows
    are job history with the same lifecycle as ``processing_jobs``: an operator
    asking to keep job history for N days means all of it.

    Only terminal rows are removed. Pending and processing jobs are in-flight
    work whose owner is still polling, and deleting one would strand both the
    poller and the staged blob.

    Args:
        lock: The platform lock provider.
        clock: The platform clock provider.
    """
    retention_days = core_config.settings.JOBS_RETENTION_DAYS
    if retention_days <= 0:
        return

    with lock.try_acquire(_PRUNE_LOCK_NAME) as acquired:
        if not acquired:
            logger.debug("Ingestion job prune: another replica holds the lock; skipping")
            return
        cutoff = clock.now() - timedelta(days=retention_days)
        with core_database.SessionLocal() as db:
            deleted = activity_ingestion_crud.delete_jobs_before(cutoff, db)
            db.commit()

    if deleted:
        logger.info(
            "Ingestion job prune: deleted finished upload job rows",
            extra=core_logger.context(deleted=deleted, retention_days=retention_days),
        )
    else:
        logger.debug("Ingestion job prune: nothing to delete")


# A pending or processing job that has not changed state for this long is no
# longer being worked on: the local pool lost it in a restart, or its loop died.
# Generous on purpose: a large local bulk import leaves later files ``pending``
# for hours, and a durable job can sit out its retries and backoff. A job that
# was in fact still queued and runs later overwrites this outcome with its own.
_STALE_JOB_AGE = timedelta(hours=24)
_STALE_LOCK_NAME = "activity_ingestion_jobs_fail_stale"


def fail_stale_ingestion_jobs(
    lock: platform_providers.LockProvider,
    clock: platform_providers.ClockProvider,
    storage: platform_providers.StorageProvider,
) -> None:
    """Fail ingestion jobs that stopped progressing, and drop their staged uploads.

    Nothing else ever closes a job whose work was lost: the prune removes only
    terminal rows, so the owner would poll ``pending`` forever and the staged
    upload would stay in storage.

    Args:
        lock: The platform lock provider.
        clock: The platform clock provider.
        storage: The blob-storage provider the uploads were staged in.
    """
    with lock.try_acquire(_STALE_LOCK_NAME) as acquired:
        if not acquired:
            logger.debug("Stale ingestion jobs: another replica holds the lock; skipping")
            return
        with core_database.SessionLocal() as db:
            failed = activity_ingestion_crud.fail_jobs_idle_since(
                clock.now() - _STALE_JOB_AGE,
                activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
                db,
            )
            db.commit()

    # After the rows are terminal, matching ``fail_ingestion_job``.
    for _job_id, staged_key in failed:
        if staged_key is not None:
            activity_ingestion_upload_entry_service.discard_staged_upload(staged_key, storage)

    if failed:
        logger.warning(
            "Failed ingestion jobs that stopped progressing",
            extra=core_logger.context(
                failed=len(failed),
                job_ids=[job_id for job_id, _ in failed],
                idle_hours=_STALE_JOB_AGE.total_seconds() / 3600,
            ),
        )
    else:
        logger.debug("Stale ingestion jobs: none found")


# Staged blobs are normally removed with their job. This sweeps what a crash, a
# lost event or a failed delete left behind. The age sits well past the longest
# time a live job can still need its blob: the stale-job reaper fails a job after
# a day.
_STAGED_UPLOAD_MIN_AGE = timedelta(days=2)
_STAGED_BLOB_BATCH_SIZE = 500
_STAGED_SWEEP_LOCK_NAME = "activity_ingestion_staged_blob_sweep"


def _aged_keys(storage: platform_providers.StorageProvider, area: str, prefix: str, older_than: float) -> Iterator[str]:
    """Yield the keys under a prefix last modified before a cutoff.

    Args:
        storage: The blob-storage provider.
        area: The storage area to scan.
        prefix: Key root to scan.
        older_than: Epoch seconds; newer blobs are skipped.
    """
    for key, modified in storage.iter_objects(area, prefix):
        if modified < older_than:
            yield key


def sweep_stale_staged_blobs(
    lock: platform_providers.LockProvider,
    clock: platform_providers.ClockProvider,
    storage: platform_providers.StorageProvider,
) -> int:
    """Delete staged upload and archive blobs that no job names and nothing will read.

    A staged blob is removed with its job, but a crash between committing the
    outcome and deleting it, or a failed delete, leaves one that no row names.

    Args:
        lock: The platform lock provider.
        clock: The platform clock provider.
        storage: The blob-storage provider.

    Returns:
        The number of blobs deleted.
    """
    removed = 0
    with lock.try_acquire(_STAGED_SWEEP_LOCK_NAME) as acquired:
        if not acquired:
            logger.debug("Staged blob sweep: another replica holds the lock; skipping")
            return 0
        prefix = activity_ingestion_upload_entry_service.UPLOAD_STAGING_KEY_PREFIX
        area = activity_ingestion_upload_entry_service.UPLOAD_STAGING_STORAGE_AREA
        upload_keys = _aged_keys(storage, area, prefix, (clock.now() - _STAGED_UPLOAD_MIN_AGE).timestamp())
        with core_database.SessionLocal() as db:
            for batch in batched(upload_keys, _STAGED_BLOB_BATCH_SIZE, strict=False):
                referenced = activity_ingestion_crud.get_referenced_staged_keys(
                    [key.removeprefix(prefix) for key in batch], db
                )
                for key in batch:
                    if key.removeprefix(prefix) not in referenced:
                        storage.delete(area, key)
                        removed += 1

    if removed:
        logger.info("Removed stale staged ingestion blobs", extra=core_logger.context(removed=removed))
    else:
        logger.debug("Staged blob sweep: nothing stale")
    return removed
