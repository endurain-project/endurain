"""Persistence for activity upload jobs.

Pure persistence: staging, parsing and executor choice live in ``upload_jobs``,
so this module never touches the filesystem and never publishes events.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity_ingestion.models as activity_ingestion_models
import modules.activities.activity_ingestion.schema as activity_ingestion_schema

logger = core_logger.get_logger(__name__)


def _to_read_schema(
    orm_job: activity_ingestion_models.ActivityUploadJob,
) -> activity_ingestion_schema.ActivityUploadJob:
    """Convert an ORM ``ActivityUploadJob`` row to its read schema.

    The single ORM→schema boundary for this module so ORM instances never leave
    ``crud``.
    """
    return activity_ingestion_schema.ActivityUploadJob(
        id=orm_job.id,
        filename=orm_job.filename,
        status=activity_ingestion_schema.UploadJobStatus(orm_job.status),
        error_code=(activity_ingestion_schema.UploadJobErrorCode(orm_job.error_code) if orm_job.error_code else None),
        activity_ids=list(orm_job.activity_ids or []),
        created_at=orm_job.created_at,
        updated_at=orm_job.updated_at,
        completed_at=orm_job.completed_at,
    )


@core_decorators.handle_db_errors
def create_upload_job(
    job_id: str,
    user_id: int,
    filename: str,
    staged_key: str,
    db: Session,
    *,
    commit: bool = True,
) -> activity_ingestion_schema.ActivityUploadJob:
    """
    Record an accepted upload in the pending state.

    Args:
        job_id: Caller-generated job identifier (UUIDv4 string).
        user_id: Owner of the upload.
        filename: Original client filename, for display only.
        staged_key: Storage key of the staged upload awaiting parsing.
        db: Database session.
        commit: Whether to commit; False lets the caller publish an event in the
            same transaction.

    Returns:
        The created upload job.

    Raises:
        HTTPException: If a database error occurs.
    """
    now = datetime.now(UTC)
    new_job = activity_ingestion_models.ActivityUploadJob(
        id=job_id,
        user_id=user_id,
        filename=filename,
        staged_key=staged_key,
        status=activity_ingestion_schema.UploadJobStatus.PENDING.value,
        created_at=now,
        updated_at=now,
    )
    db.add(new_job)
    if commit:
        db.commit()
    else:
        db.flush()
    return _to_read_schema(new_job)


@core_decorators.handle_db_errors
def get_upload_job(
    job_id: str,
    user_id: int,
    db: Session,
) -> activity_ingestion_schema.ActivityUploadJob | None:
    """
    Retrieve one upload job belonging to a user.

    Always filtered by ``user_id``: an upload job id is a bearer-ish handle, and
    scoping the read here means no caller can accidentally expose another user's
    job by forgetting the check.

    Args:
        job_id: The job identifier.
        user_id: Owner the job must belong to.
        db: Database session.

    Returns:
        The upload job, or None if it does not exist or belongs to someone else.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(activity_ingestion_models.ActivityUploadJob).where(
        activity_ingestion_models.ActivityUploadJob.id == job_id,
        activity_ingestion_models.ActivityUploadJob.user_id == user_id,
    )
    orm_job = db.scalars(stmt).first()
    return _to_read_schema(orm_job) if orm_job else None


@core_decorators.handle_db_errors
def get_job_work_item(job_id: str, db: Session) -> tuple[int, str] | None:
    """
    Read the owner and staged key of a job, for the background executor.

    Not user-scoped, unlike :func:`get_upload_job`: the caller here is the
    worker acting on an event it was handed, not an HTTP client naming a job.
    Returning the stored ``user_id`` is what keeps the parse attributed to the
    uploader even if the event payload were tampered with.

    Args:
        job_id: The job identifier.
        db: Database session.

    Returns:
        A ``(user_id, staged_key)`` pair, or None if the job is unknown or its
        upload was already consumed.

    Raises:
        HTTPException: If a database error occurs.
    """
    orm_job = db.get(activity_ingestion_models.ActivityUploadJob, job_id)
    if orm_job is None or orm_job.staged_key is None:
        return None
    return orm_job.user_id, orm_job.staged_key


@core_decorators.handle_db_errors
def mark_processing(job_id: str, db: Session) -> None:
    """
    Move a job to the processing state.

    Args:
        job_id: The job identifier.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If a database error occurs.
    """
    orm_job = db.get(activity_ingestion_models.ActivityUploadJob, job_id)
    if orm_job is None:
        return
    orm_job.status = activity_ingestion_schema.UploadJobStatus.PROCESSING.value
    orm_job.updated_at = datetime.now(UTC)
    db.commit()


@core_decorators.handle_db_errors
def mark_completed(job_id: str, activity_ids: list[int], db: Session) -> None:
    """
    Move a job to the completed state and record what it created.

    Args:
        job_id: The job identifier.
        activity_ids: Ids of the activities the import created.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If a database error occurs.
    """
    orm_job = db.get(activity_ingestion_models.ActivityUploadJob, job_id)
    if orm_job is None:
        return
    now = datetime.now(UTC)
    orm_job.status = activity_ingestion_schema.UploadJobStatus.COMPLETED.value
    orm_job.activity_ids = activity_ids
    orm_job.error_code = None
    orm_job.staged_key = None
    orm_job.updated_at = now
    orm_job.completed_at = now
    db.commit()


@core_decorators.handle_db_errors
def mark_failed(
    job_id: str,
    error_code: activity_ingestion_schema.UploadJobErrorCode,
    db: Session,
) -> None:
    """
    Move a job to the failed state with a sanitized reason.

    Args:
        job_id: The job identifier.
        error_code: Sanitized failure reason shown to the owner.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If a database error occurs.
    """
    orm_job = db.get(activity_ingestion_models.ActivityUploadJob, job_id)
    if orm_job is None:
        return
    now = datetime.now(UTC)
    orm_job.status = activity_ingestion_schema.UploadJobStatus.FAILED.value
    orm_job.error_code = error_code.value
    orm_job.staged_key = None
    orm_job.updated_at = now
    orm_job.completed_at = now
    db.commit()


@core_decorators.handle_db_errors
def delete_jobs_before(cutoff: datetime, db: Session) -> int:
    """
    Delete terminal upload jobs older than a cutoff.

    Args:
        cutoff: Jobs that reached a terminal state before this are removed.
        db: Database session.

    Returns:
        Number of rows deleted.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(activity_ingestion_models.ActivityUploadJob).where(
        activity_ingestion_models.ActivityUploadJob.completed_at.is_not(None),
        activity_ingestion_models.ActivityUploadJob.completed_at < cutoff,
    )
    stale = list(db.scalars(stmt).all())
    for orm_job in stale:
        db.delete(orm_job)
    db.commit()
    return len(stale)
