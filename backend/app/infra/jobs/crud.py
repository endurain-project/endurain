"""CRUD for ``processing_jobs`` — the durable, Postgres-as-truth work queue.

Every query is portable so the same code runs on PostgreSQL in production and
SQLite in tests. The claim uses ``SELECT ... FOR UPDATE SKIP LOCKED`` on
PostgreSQL (concurrent workers never grab the same row); on SQLite the clause is
omitted, which is correct because tests are single-threaded. Callers pass an
explicit ``now`` (from the ``ClockProvider``) so lease, backoff, and reaping are
deterministic under test.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

import infra.jobs.backoff as jobs_backoff
import infra.jobs.schema as jobs_schema
from infra.events import Event
from infra.jobs.models import ProcessingJob

STATUS_PENDING = "pending"
STATUS_CLAIMED = "claimed"
STATUS_COMPLETED = "completed"
STATUS_DEAD_LETTER = "dead_letter"

# Cap stored failure text so a pathological exception cannot bloat a row.
_MAX_ERROR_LEN = 4000

_CONFLICT_KEYS = ["event_id", "subscriber_id"]


def enqueue_job(
    event: Event,
    subscriber_id: str,
    *,
    max_attempts: int,
    now: datetime,
    db: Session,
    available_at: datetime | None = None,
) -> ProcessingJob | None:
    """
    Enqueue one durable job for ``(event, subscriber_id)``, idempotently.

    The ``(event_id, subscriber_id)`` uniqueness makes a repeat enqueue a no-op,
    so the same subscriber never runs twice for the same event (idempotent
    consumer). Because each call mints a fresh job id, the freshly inserted row
    is returned only when this call actually inserted it.

    Args:
        event: The originating event envelope.
        subscriber_id: The durable subscriber this job runs.
        max_attempts: Attempt ceiling before the job is dead-lettered.
        now: Current instant (used for created/updated/available timestamps).
        db: Active database session.
        available_at: Earliest claim instant; defaults to ``now``.

    Returns:
        The inserted job, or ``None`` when a job for this ``(event, subscriber)``
        already existed.
    """
    job_id = str(uuid.uuid4())
    values = {
        "id": job_id,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "subscriber_id": subscriber_id,
        "source": event.source,
        "payload": event.payload,
        "job_metadata": event.metadata or None,
        "status": STATUS_PENDING,
        "attempts": 0,
        "max_attempts": max_attempts,
        "available_at": available_at or now,
        "created_at": now,
        "updated_at": now,
    }
    db.execute(_insert_ignoring_duplicate(values, db))
    db.commit()
    # Returns the row only when this call inserted it: a skipped conflict leaves
    # our unique job_id absent, so ``get`` yields None for a duplicate enqueue.
    return db.get(ProcessingJob, job_id)


def claim_jobs(
    *,
    worker_id: str,
    limit: int,
    lease_seconds: int,
    now: datetime,
    db: Session,
) -> list[ProcessingJob]:
    """
    Atomically claim up to ``limit`` due jobs, taking a time-bounded lease.

    Selects ``pending`` rows whose ``available_at`` has passed, locking them with
    ``FOR UPDATE SKIP LOCKED`` on PostgreSQL so concurrent workers claim disjoint
    sets, then marks them ``claimed`` (incrementing ``attempts`` and stamping the
    lease). The attempt is counted at claim time so a worker that crashes
    mid-run still consumes an attempt, bounding crash loops.

    Args:
        worker_id: Identifier of the claiming worker (the lease holder).
        limit: Maximum number of jobs to claim.
        lease_seconds: Lease duration; the reaper requeues jobs past it.
        now: Current instant.
        db: Active database session.

    Returns:
        The claimed jobs, oldest-available first.
    """
    id_stmt = (
        select(ProcessingJob.id)
        .where(ProcessingJob.status == STATUS_PENDING, ProcessingJob.available_at <= now)
        .order_by(ProcessingJob.available_at)
        .limit(limit)
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        id_stmt = id_stmt.with_for_update(skip_locked=True)  # pragma: no cover - Postgres-only path
    job_ids = list(db.execute(id_stmt).scalars().all())
    if not job_ids:
        db.commit()  # end the transaction so FOR UPDATE locks are released
        return []
    db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id.in_(job_ids))
        .values(
            status=STATUS_CLAIMED,
            attempts=ProcessingJob.attempts + 1,
            locked_by=worker_id,
            locked_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )
    )
    db.commit()
    claimed = (
        db.execute(select(ProcessingJob).where(ProcessingJob.id.in_(job_ids)).order_by(ProcessingJob.available_at))
        .scalars()
        .all()
    )
    return list(claimed)


def mark_job_completed(job_id: str, *, now: datetime, db: Session) -> None:
    """
    Mark a claimed job ``completed`` and release its lease.

    Args:
        job_id: The job to complete.
        now: Current instant.
        db: Active database session.

    Returns:
        None.
    """
    db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(
            status=STATUS_COMPLETED,
            completed_at=now,
            updated_at=now,
            last_error=None,
            locked_by=None,
            lease_expires_at=None,
        )
    )
    db.commit()


def mark_job_failed(
    job_id: str,
    error_message: str,
    *,
    base_seconds: float,
    max_seconds: float,
    now: datetime,
    db: Session,
) -> str:
    """
    Record a failed attempt: reschedule with backoff, or dead-letter if exhausted.

    Args:
        job_id: The job that failed.
        error_message: The failure reason (truncated for storage).
        base_seconds: Backoff base delay.
        max_seconds: Backoff ceiling.
        now: Current instant.
        db: Active database session.

    Returns:
        The job's new status (``pending`` when rescheduled, ``dead_letter`` when
        the attempt ceiling was reached), or the empty string when the job was
        not found.
    """
    job = db.get(ProcessingJob, job_id)
    if job is None:
        return ""
    truncated = error_message[:_MAX_ERROR_LEN]
    if job.attempts >= job.max_attempts:
        db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .values(
                status=STATUS_DEAD_LETTER,
                last_error=truncated,
                completed_at=now,
                updated_at=now,
                locked_by=None,
                lease_expires_at=None,
            )
        )
        db.commit()
        return STATUS_DEAD_LETTER
    delay = jobs_backoff.backoff_seconds(job.attempts, base_seconds=base_seconds, max_seconds=max_seconds)
    db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(
            status=STATUS_PENDING,
            last_error=truncated,
            available_at=now + timedelta(seconds=delay),
            updated_at=now,
            locked_by=None,
            locked_at=None,
            lease_expires_at=None,
        )
    )
    db.commit()
    return STATUS_PENDING


def reclaim_expired_leases(*, now: datetime, db: Session, limit: int = 100) -> int:
    """
    Return jobs whose lease expired (a crashed worker) to a runnable state.

    Exhausted rows (``attempts >= max_attempts``) are dead-lettered; the rest are
    made ``pending`` and immediately available again.

    Args:
        now: Current instant.
        db: Active database session.
        limit: Maximum number of expired leases to reclaim in one pass.

    Returns:
        The number of jobs reclaimed (requeued plus dead-lettered).
    """
    id_stmt = (
        select(ProcessingJob.id)
        .where(ProcessingJob.status == STATUS_CLAIMED, ProcessingJob.lease_expires_at < now)
        .limit(limit)
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        id_stmt = id_stmt.with_for_update(skip_locked=True)  # pragma: no cover - Postgres-only path
    job_ids = list(db.execute(id_stmt).scalars().all())
    if not job_ids:
        db.commit()
        return 0
    db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id.in_(job_ids),
            ProcessingJob.attempts >= ProcessingJob.max_attempts,
        )
        .values(
            status=STATUS_DEAD_LETTER,
            last_error="lease expired; max attempts exhausted",
            completed_at=now,
            updated_at=now,
            locked_by=None,
            lease_expires_at=None,
        )
    )
    db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id.in_(job_ids),
            ProcessingJob.attempts < ProcessingJob.max_attempts,
        )
        .values(
            status=STATUS_PENDING,
            last_error="lease expired; requeued",
            available_at=now,
            updated_at=now,
            locked_by=None,
            locked_at=None,
            lease_expires_at=None,
        )
    )
    db.commit()
    return len(job_ids)


def get_job(job_id: str, db: Session) -> ProcessingJob | None:
    """
    Fetch a job by id.

    Args:
        job_id: The job identifier.
        db: Active database session.

    Returns:
        The job, or ``None`` when it does not exist.
    """
    return db.get(ProcessingJob, job_id)


def get_jobs_summary(db: Session, *, hours: int = 24, dead_letter_limit: int = 50) -> jobs_schema.JobsSummary:
    """
    Aggregate ``processing_jobs`` into the admin-dashboard payload.

    Args:
        db: Active database session.
        hours: Look-back window for the status/subscriber counts.
        dead_letter_limit: Maximum dead-letter jobs to return for inspection.

    Returns:
        The durable-jobs summary — window counts, per-subscriber breakdown,
        oldest pending age, and the current dead-letter queue.
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=hours)
    rows = db.execute(
        select(ProcessingJob.subscriber_id, ProcessingJob.event_type, ProcessingJob.status, func.count())
        .where(ProcessingJob.created_at >= window_start)
        .group_by(ProcessingJob.subscriber_id, ProcessingJob.event_type, ProcessingJob.status)
    ).all()
    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[str, int] = defaultdict(int)
    for subscriber_id, event_type, status, count in rows:
        counts[(subscriber_id, event_type)][status] += count
        totals[status] += count
    by_subscriber = [
        jobs_schema.JobSubscriberStats(
            subscriber_id=subscriber_id,
            event_type=event_type,
            total=sum(status_counts.values()),
            pending=status_counts.get(STATUS_PENDING, 0),
            claimed=status_counts.get(STATUS_CLAIMED, 0),
            completed=status_counts.get(STATUS_COMPLETED, 0),
            dead_letter=status_counts.get(STATUS_DEAD_LETTER, 0),
        )
        for (subscriber_id, event_type), status_counts in sorted(counts.items())
    ]
    oldest_pending = db.execute(
        select(func.min(ProcessingJob.created_at)).where(ProcessingJob.status.in_((STATUS_PENDING, STATUS_CLAIMED)))
    ).scalar()
    dead_letter_jobs = (
        db.execute(
            select(ProcessingJob)
            .where(ProcessingJob.status == STATUS_DEAD_LETTER)
            .order_by(ProcessingJob.updated_at.desc())
            .limit(dead_letter_limit)
        )
        .scalars()
        .all()
    )
    return jobs_schema.JobsSummary(
        window_hours=hours,
        total_jobs=sum(totals.values()),
        pending=totals.get(STATUS_PENDING, 0),
        claimed=totals.get(STATUS_CLAIMED, 0),
        completed=totals.get(STATUS_COMPLETED, 0),
        dead_letter=totals.get(STATUS_DEAD_LETTER, 0),
        oldest_pending_seconds=_age_seconds(oldest_pending, now),
        by_subscriber=by_subscriber,
        recent_dead_letter=[jobs_schema.DeadLetterJob.model_validate(job) for job in dead_letter_jobs],
    )


def replay_dead_letter_job(job_id: str, *, now: datetime, db: Session) -> bool:
    """
    Requeue a dead-lettered job for a fresh run.

    Resets the job to ``pending`` with a full attempt budget so the worker picks
    it up again. Only a job currently in ``dead_letter`` is affected.

    Args:
        job_id: The job to replay.
        now: Current instant (the new availability time).
        db: Active database session.

    Returns:
        True when a dead-letter job was requeued; False when none matched.
    """
    job = db.get(ProcessingJob, job_id)
    if job is None or job.status != STATUS_DEAD_LETTER:
        return False
    db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id, ProcessingJob.status == STATUS_DEAD_LETTER)
        .values(
            status=STATUS_PENDING,
            attempts=0,
            available_at=now,
            updated_at=now,
            last_error=None,
            locked_by=None,
            locked_at=None,
            lease_expires_at=None,
            completed_at=None,
        )
    )
    db.commit()
    return True


def _age_seconds(moment: datetime | None, now: datetime) -> float | None:
    """Age of ``moment`` relative to ``now`` in seconds (SQLite returns naive datetimes)."""
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (now - moment).total_seconds()


def _insert_ignoring_duplicate(values: dict, db: Session):
    """
    Build a dialect-appropriate ``INSERT ... ON CONFLICT DO NOTHING`` statement.

    Args:
        values: Column values for the new row.
        db: Active database session (used only for dialect detection).

    Returns:
        An executable insert statement that ignores a duplicate
        ``(event_id, subscriber_id)``.
    """
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":  # pragma: no cover - exercised on Postgres, not in SQLite tests
        return pg_insert(ProcessingJob).values(**values).on_conflict_do_nothing(index_elements=_CONFLICT_KEYS)
    if dialect == "sqlite":
        return sqlite_insert(ProcessingJob).values(**values).on_conflict_do_nothing(index_elements=_CONFLICT_KEYS)
    return insert(ProcessingJob).values(**values)  # pragma: no cover - defensive fallback
