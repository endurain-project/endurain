"""Persistence for activity ingestion jobs.

Pure persistence: staging, parsing and executor choice live in ``service``,
so this module never touches the filesystem and never publishes events.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, or_, select, update
from sqlalchemy.orm import Session

import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts
import modules.activities.activity_ingestion.models as activity_ingestion_models
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.serializers as activity_ingestion_serializers


def _get_open_job_for_update(job_id: str, db: Session) -> activity_ingestion_models.ActivityIngestionJob | None:
    """Load a job row under a row lock, unless it is unknown or already terminal.

    The lock serializes concurrent writers of the same job across processes, and
    the terminal check keeps a late writer (a worker whose lease expired and was
    reclaimed, or the stale-job reaper) from overwriting the outcome another
    caller already recorded.

    Args:
        job_id: The job identifier.
        db: Database session.

    Returns:
        The locked, non-terminal job row, or ``None``.
    """
    orm_job = db.get(activity_ingestion_models.ActivityIngestionJob, job_id, with_for_update=True)
    if orm_job is None or orm_job.completed_at is not None:
        return None
    return orm_job


def create_ingestion_job(
    job_id: str,
    user_id: int,
    kind: activity_ingestion_constants.IngestionJobKind,
    db: Session,
    *,
    filename: str | None = None,
    staged_key: str | None = None,
    idempotency_key: str | None = None,
    request_fingerprint: str | None = None,
    provider: str | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    import_source: str | None = None,
    files_total: int | None = None,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Stage an accepted ingestion request in the pending state (not committed).

    Args:
        job_id: Caller-generated job identifier (UUIDv4 string).
        user_id: Owner of the request.
        kind: Whether this job imports an upload or syncs from providers.
        db: Database session.
        filename: Original client filename; uploads only, for display.
        staged_key: Storage key of the staged upload awaiting parsing; uploads
            only.
        idempotency_key: Client-supplied ``Idempotency-Key``, unique per user
            and kind.
        request_fingerprint: SHA-256 of the uploaded bytes, stored so a reused
            key carrying different content can be rejected.
        provider: The provider a refresh syncs; ``None`` for every linked one.
        window_start: Start of the window a refresh fetches; refresh only.
        window_end: End of the window a refresh fetches; refresh only.
        import_source: The archive format a bulk import reads; bulk import only.
        files_total: Importable files in a bulk import's archive; bulk import only.

    Returns:
        The created ingestion job.

    Raises:
        IntegrityError: If the user already has a job with this idempotency key.
    """
    now = datetime.now(UTC)
    new_job = activity_ingestion_models.ActivityIngestionJob(
        id=job_id,
        user_id=user_id,
        kind=kind.value,
        filename=filename,
        staged_key=staged_key,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        provider=provider,
        window_start=window_start,
        window_end=window_end,
        import_source=import_source,
        files_total=files_total,
        files_done=0 if import_source is not None else None,
        files_failed=0 if import_source is not None else None,
        status=activity_ingestion_constants.IngestionJobStatus.PENDING.value,
        created_at=now,
        updated_at=now,
    )
    db.add(new_job)
    db.flush()
    return activity_ingestion_serializers.to_read_schema(new_job)


def get_ingestion_job(
    job_id: str,
    user_id: int,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead | None:
    """Retrieve one ingestion job belonging to a user.

    Always filtered by ``user_id``: a job id is a bearer-ish handle, and
    scoping the read here means no caller can accidentally expose another user's
    job by forgetting the check.

    Args:
        job_id: The job identifier.
        user_id: Owner the job must belong to.
        db: Database session.

    Returns:
        The ingestion job, or None if it does not exist or belongs to someone else.
    """
    stmt = select(activity_ingestion_models.ActivityIngestionJob).where(
        activity_ingestion_models.ActivityIngestionJob.id == job_id,
        activity_ingestion_models.ActivityIngestionJob.user_id == user_id,
    )
    orm_job = db.scalars(stmt).first()
    return activity_ingestion_serializers.to_read_schema(orm_job) if orm_job else None


def get_job_work_item(job_id: str, db: Session) -> tuple[int, str] | None:
    """Read the owner and staged key of a job, for the background executor.

    Not user-scoped, unlike :func:`get_ingestion_job`: the caller here is the
    worker acting on an event it was handed, not an HTTP client naming a job.
    Returning the stored ``user_id`` is what keeps the parse attributed to the
    uploader even if the event payload were tampered with.

    Args:
        job_id: The job identifier.
        db: Database session.

    Returns:
        A ``(user_id, staged_key)`` pair, or None if the job is unknown or its
        upload was already consumed.
    """
    orm_job = db.get(activity_ingestion_models.ActivityIngestionJob, job_id)
    if orm_job is None or orm_job.staged_key is None:
        return None
    return orm_job.user_id, orm_job.staged_key


def get_job_for_idempotency(
    idempotency_key: str,
    user_id: int,
    kind: activity_ingestion_constants.IngestionJobKind,
    db: Session,
) -> tuple[activity_ingestion_schema.ActivityIngestionJobRead, str | None] | None:
    """Retrieve a user's job by the idempotency key it was accepted with.

    Returns the stored request fingerprint alongside the job: the caller has to
    compare it before treating the request as a replay, because the same key
    carrying different content is a client error rather than a repeat.

    Scoped to the user and kind for the same reason the constraint is: a key is
    only meaningful within the client that generated it, and an unscoped lookup
    would let one caller discover another's job by guessing keys.

    Args:
        idempotency_key: The client-supplied key.
        user_id: Owner the job must belong to.
        kind: The job kind the key was used on.
        db: Database session.

    Returns:
        A ``(job, fingerprint)`` pair, or None if this user has not used that
        key for that kind.
    """
    stmt = select(activity_ingestion_models.ActivityIngestionJob).where(
        activity_ingestion_models.ActivityIngestionJob.idempotency_key == idempotency_key,
        activity_ingestion_models.ActivityIngestionJob.user_id == user_id,
        activity_ingestion_models.ActivityIngestionJob.kind == kind.value,
    )
    orm_job = db.scalars(stmt).first()
    return (activity_ingestion_serializers.to_read_schema(orm_job), orm_job.request_fingerprint) if orm_job else None


def release_idempotency_key(job_id: str, db: Session) -> None:
    """Stage freeing a job's idempotency key so a new request can use it (not committed).

    The job row stays, so its history is intact; only the key (and the fingerprint
    that guarded it) is dropped.

    Args:
        job_id: The job identifier.
        db: Database session.
    """
    model = activity_ingestion_models.ActivityIngestionJob
    db.execute(update(model).where(model.id == job_id).values(idempotency_key=None, request_fingerprint=None))
    db.flush()


def get_job_owner(job_id: str, db: Session) -> int | None:
    """Read the owner of a job, for the background executor.

    Not user-scoped, unlike :func:`get_ingestion_job`: the caller is the worker
    acting on an event it was handed, not an HTTP client naming a job. Reading
    the owner from the row rather than the event payload is what keeps the sync
    attributed to the requester even if the payload were tampered with.

    Args:
        job_id: The job identifier.
        db: Database session.

    Returns:
        The owning user id, or None if the job is unknown.
    """
    orm_job = db.get(activity_ingestion_models.ActivityIngestionJob, job_id)
    return orm_job.user_id if orm_job else None


def get_refresh_scope(job_id: str, db: Session) -> tuple[int, str | None, datetime | None, datetime | None] | None:
    """Read what a refresh job was asked to sync, for the background executor.

    Not user-scoped, for the same reason as :func:`get_job_owner`: the owner and
    scope come from the row, not from an event payload that could be tampered
    with.

    Args:
        job_id: The job identifier.
        db: Database session.

    Returns:
        ``(user_id, provider, window_start, window_end)``, or ``None`` when the
        job is unknown.
    """
    orm_job = db.get(activity_ingestion_models.ActivityIngestionJob, job_id)
    if orm_job is None:
        return None
    return orm_job.user_id, orm_job.provider, orm_job.window_start, orm_job.window_end


def get_user_ids_with_active_refresh(user_ids: Sequence[int], db: Session) -> set[int]:
    """Return which of the given users already have a refresh queued or running.

    Lets the scheduled fan-out skip a user whose previous refresh has not finished
    instead of piling a second one behind it.

    Args:
        user_ids: Candidate users.
        db: Database session.

    Returns:
        The subset with a pending or processing refresh job.
    """
    if not user_ids:
        return set()
    stmt = select(activity_ingestion_models.ActivityIngestionJob.user_id).where(
        activity_ingestion_models.ActivityIngestionJob.user_id.in_(user_ids),
        activity_ingestion_models.ActivityIngestionJob.kind
        == activity_ingestion_constants.IngestionJobKind.REFRESH.value,
        activity_ingestion_models.ActivityIngestionJob.completed_at.is_(None),
    )
    return set(db.scalars(stmt).all())


def get_active_bulk_import_job_id(user_id: int, db: Session) -> str | None:
    """Return the id of the user's bulk import that has not finished, if any.

    Args:
        user_id: The user.
        db: Database session.

    Returns:
        The running job's id, or ``None``.
    """
    stmt = select(activity_ingestion_models.ActivityIngestionJob.id).where(
        activity_ingestion_models.ActivityIngestionJob.user_id == user_id,
        activity_ingestion_models.ActivityIngestionJob.kind
        == activity_ingestion_constants.IngestionJobKind.BULK_IMPORT.value,
        activity_ingestion_models.ActivityIngestionJob.completed_at.is_(None),
    )
    return db.scalars(stmt).first()


def get_bulk_import_state(job_id: str, db: Session) -> activity_ingestion_contracts.BulkImportState | None:
    """Read a bulk-import job's resume state, for the background executor.

    Not user-scoped, for the same reason as :func:`get_job_owner`.

    Args:
        job_id: The job identifier.
        db: Database session.

    Returns:
        The state, or ``None`` when the job is unknown or is not a bulk import.
    """
    orm_job = db.get(activity_ingestion_models.ActivityIngestionJob, job_id)
    if orm_job is None or orm_job.kind != activity_ingestion_constants.IngestionJobKind.BULK_IMPORT.value:
        return None
    return activity_ingestion_contracts.BulkImportState(
        user_id=orm_job.user_id,
        import_source=orm_job.import_source or "",
        staged_key=orm_job.staged_key,
        cursor=orm_job.cursor,
        files_total=orm_job.files_total or 0,
        files_done=orm_job.files_done or 0,
        files_failed=orm_job.files_failed or 0,
        created_at=orm_job.created_at,
        finished=orm_job.completed_at is not None,
    )


def attach_bulk_archive(job_id: str, staged_key: str, files_total: int, db: Session) -> None:
    """Stage recording the archive a bulk import will read (not committed).

    Args:
        job_id: The job identifier.
        staged_key: Storage key of the staged archive.
        files_total: Importable files it holds.
        db: Database session.
    """
    orm_job = db.get(activity_ingestion_models.ActivityIngestionJob, job_id)
    if orm_job is None:
        return
    orm_job.staged_key = staged_key
    orm_job.files_total = files_total
    orm_job.updated_at = func.now()
    db.flush()


def record_bulk_progress(
    job_id: str,
    cursor: str | None,
    files_done: int,
    files_failed: int,
    db: Session,
    *,
    release: bool = False,
) -> None:
    """Stage a bulk import's resume point and counters (not committed).

    Args:
        job_id: The job identifier.
        cursor: The last member handled.
        files_done: Files imported so far.
        files_failed: Files that could not be imported.
        db: Database session.
        release: Leave the job ``pending`` instead of ``processing``, so the
            continuation queued with this checkpoint can claim it.
    """
    orm_job = _get_open_job_for_update(job_id, db)
    if orm_job is None:
        return
    orm_job.status = (
        activity_ingestion_constants.IngestionJobStatus.PENDING.value
        if release
        else activity_ingestion_constants.IngestionJobStatus.PROCESSING.value
    )
    orm_job.cursor = cursor
    orm_job.files_done = files_done
    orm_job.files_failed = files_failed
    orm_job.updated_at = func.now()
    db.flush()


def mark_bulk_completed(job_id: str, cursor: str | None, files_done: int, files_failed: int, db: Session) -> None:
    """Stage a bulk import as finished (not committed).

    A finished import with failed files is still ``completed``: the counters say
    how many, and each failed file was recorded as it happened.

    Args:
        job_id: The job identifier.
        cursor: The last member handled.
        files_done: Files imported.
        files_failed: Files that could not be imported.
        db: Database session.
    """
    orm_job = _get_open_job_for_update(job_id, db)
    if orm_job is None:
        return
    now = datetime.now(UTC)
    orm_job.status = activity_ingestion_constants.IngestionJobStatus.COMPLETED.value
    orm_job.error_code = None
    orm_job.cursor = cursor
    orm_job.files_done = files_done
    orm_job.files_failed = files_failed
    orm_job.staged_key = None
    orm_job.updated_at = now
    orm_job.completed_at = now
    db.flush()


def mark_processing(job_id: str, db: Session, *, lease: timedelta) -> bool:
    """Stage the claim of a job for execution (not committed).

    One conditional ``UPDATE``, so of two concurrent deliveries of the same job
    only one claims it. A job is claimable while it is ``pending`` or while its
    last claim is older than ``lease`` (the worker died or its lease expired); a
    job that reached a terminal state never is.

    Claim timestamps come from the database clock and the cutoff is derived from
    it, so replicas with skewed clocks agree on whether a claim has expired.

    Args:
        job_id: The job identifier.
        db: Database session.
        lease: A ``processing`` job last touched longer ago than this is treated
            as abandoned and may be claimed again.

    Returns:
        ``True`` when this caller now owns the job, ``False`` when it is unknown,
        finished, or being worked on by someone else.
    """
    model = activity_ingestion_models.ActivityIngestionJob
    stale_before = db.scalars(select(func.now())).one() - lease
    stmt = (
        update(model)
        .where(
            model.id == job_id,
            model.completed_at.is_(None),
            or_(
                model.status == activity_ingestion_constants.IngestionJobStatus.PENDING.value,
                model.updated_at < stale_before,
            ),
        )
        .values(
            status=activity_ingestion_constants.IngestionJobStatus.PROCESSING.value,
            updated_at=func.now(),
        )
    )
    result = cast("CursorResult[Any]", db.execute(stmt))
    db.flush()
    return result.rowcount == 1


def release_job(job_id: str, db: Session) -> None:
    """Stage returning a claimed job to ``pending`` so a retry can claim it (not committed).

    Args:
        job_id: The job identifier.
        db: Database session.
    """
    model = activity_ingestion_models.ActivityIngestionJob
    stmt = (
        update(model)
        .where(
            model.id == job_id,
            model.completed_at.is_(None),
            model.status == activity_ingestion_constants.IngestionJobStatus.PROCESSING.value,
        )
        .values(status=activity_ingestion_constants.IngestionJobStatus.PENDING.value, updated_at=func.now())
    )
    db.execute(stmt)
    db.flush()


def mark_completed(job_id: str, activity_ids: list[int], db: Session) -> None:
    """Stage a move of a job to the completed state and record what it created.

    Args:
        job_id: The job identifier.
        activity_ids: Ids of the activities the import created.
        db: Database session.
    """
    orm_job = _get_open_job_for_update(job_id, db)
    if orm_job is None:
        return
    now = datetime.now(UTC)
    orm_job.status = activity_ingestion_constants.IngestionJobStatus.COMPLETED.value
    orm_job.activity_ids = activity_ids
    orm_job.error_code = None
    orm_job.staged_key = None
    orm_job.updated_at = now
    orm_job.completed_at = now
    db.flush()


def _fail(
    orm_job: activity_ingestion_models.ActivityIngestionJob,
    error_code: activity_ingestion_constants.IngestionJobErrorCode,
    now: datetime,
) -> None:
    """Move a loaded job row to the failed state."""
    orm_job.status = activity_ingestion_constants.IngestionJobStatus.FAILED.value
    orm_job.error_code = error_code.value
    orm_job.staged_key = None
    orm_job.updated_at = now
    orm_job.completed_at = now


def mark_failed(
    job_id: str,
    error_code: activity_ingestion_constants.IngestionJobErrorCode,
    db: Session,
) -> None:
    """Stage a move of a job to the failed state with a sanitized reason.

    Args:
        job_id: The job identifier.
        error_code: Sanitized failure reason shown to the owner.
        db: Database session.
    """
    orm_job = _get_open_job_for_update(job_id, db)
    if orm_job is None:
        return
    _fail(orm_job, error_code, datetime.now(UTC))
    db.flush()


def fail_jobs_idle_since(
    cutoff: datetime,
    error_code: activity_ingestion_constants.IngestionJobErrorCode,
    db: Session,
) -> list[tuple[str, str | None]]:
    """Stage the failure of non-terminal jobs that have not changed state since a cutoff.

    Args:
        cutoff: Pending or processing jobs last updated before this are failed.
        error_code: Sanitized failure reason shown to the owner.
        db: Database session.

    Returns:
        ``(job id, staged key)`` for each failed job; the key is the staged upload
        the job still held, or ``None``.
    """
    stmt = select(activity_ingestion_models.ActivityIngestionJob).where(
        activity_ingestion_models.ActivityIngestionJob.completed_at.is_(None),
        activity_ingestion_models.ActivityIngestionJob.updated_at < cutoff,
    )
    # Rows a worker is writing right now are skipped: they are not idle, and
    # failing them would overwrite the outcome the worker is about to commit.
    stmt = stmt.with_for_update(skip_locked=True)
    now = datetime.now(UTC)
    failed: list[tuple[str, str | None]] = []
    for orm_job in db.scalars(stmt).all():
        failed.append((orm_job.id, orm_job.staged_key))
        _fail(orm_job, error_code, now)
    db.flush()
    return failed


def get_referenced_staged_keys(staged_keys: Sequence[str], db: Session) -> set[str]:
    """Return which of the given staged-upload keys a job row still names.

    Args:
        staged_keys: Candidate staged-upload keys.
        db: Database session.

    Returns:
        The subset that some job references.
    """
    if not staged_keys:
        return set()
    stmt = select(activity_ingestion_models.ActivityIngestionJob.staged_key).where(
        activity_ingestion_models.ActivityIngestionJob.staged_key.in_(staged_keys)
    )
    return {key for key in db.scalars(stmt).all() if key is not None}


def delete_jobs_before(cutoff: datetime, db: Session) -> int:
    """Stage the deletion of terminal ingestion jobs older than a cutoff.

    Args:
        cutoff: Jobs that reached a terminal state before this are removed.
        db: Database session.

    Returns:
        Number of rows deleted.
    """
    stmt = delete(activity_ingestion_models.ActivityIngestionJob).where(
        activity_ingestion_models.ActivityIngestionJob.completed_at.is_not(None),
        activity_ingestion_models.ActivityIngestionJob.completed_at < cutoff,
    )
    result = cast("CursorResult[Any]", db.execute(stmt))
    db.flush()
    return result.rowcount
