"""CRUD for the event_log table — lifecycle writes and dashboard aggregates.

The recording helpers write the event lifecycle: ``record_published`` /
``mark_processing`` / ``mark_completed`` / ``mark_failed`` for bus-delivered
events (via the recorder in :mod:`core.event_log.recorder`), and ``record_queued``
for events handed to the durable job queue (via the publish facade). The
``get_event_log_summary`` helper powers the admin dashboard. Every query here is
portable SQL so the same code runs on PostgreSQL in production and SQLite in tests.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

import core.event_log.schema as event_log_schema
from core.event_log.models import EventLog
from core.platform.events import Event

_STATUS_PUBLISHED = "published"
_STATUS_QUEUED = "queued"
_STATUS_PROCESSING = "processing"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"
_STATUS_DEAD_LETTER = "dead_letter"

# Cap stored failure text so a pathological exception cannot bloat a row.
_MAX_ERROR_LEN = 4000


def record_published(event: Event, db: Session) -> None:
    """
    Insert the initial ``published`` row for a freshly published event.

    Args:
        event: The event envelope being published.
        db: Active database session.

    Returns:
        None.
    """
    db.add(
        EventLog(
            id=event.event_id,
            event_type=event.event_type,
            event_source=event.source,
            event_payload=event.payload,
            event_metadata=event.metadata or None,
            status=_STATUS_PUBLISHED,
            retry_count=event.retry_count,
        )
    )
    db.commit()


def record_queued(event: Event, db: Session) -> None:
    """
    Insert a terminal ``queued`` row for an event handed to the durable job queue.

    Durable events are executed by the worker (tracked per-subscriber in
    ``processing_jobs``), not by the event bus, so ``queued`` is terminal from the
    event_log's perspective: it keeps durable events visible in the dashboard
    without counting them as perpetually ``pending``. Execution detail lives in
    the Jobs dashboard.

    Args:
        event: The event envelope being staged for durable delivery.
        db: Active database session.

    Returns:
        None.
    """
    db.add(
        EventLog(
            id=event.event_id,
            event_type=event.event_type,
            event_source=event.source,
            event_payload=event.payload,
            event_metadata=event.metadata or None,
            status=_STATUS_QUEUED,
            retry_count=event.retry_count,
        )
    )
    db.commit()


def mark_processing(event_id: str, worker_id: str, db: Session) -> None:
    """
    Transition an event to ``processing`` when a consumer picks it up.

    Args:
        event_id: The event_id (primary key).
        worker_id: The process/consumer handling the event.
        db: Active database session.

    Returns:
        None.
    """
    db.execute(
        update(EventLog)
        .where(EventLog.id == event_id)
        .values(status=_STATUS_PROCESSING, worker_id=worker_id, processed_at=func.now())
    )
    db.commit()


def mark_completed(event_id: str, handler_name: str | None, processing_time_ms: int, db: Session) -> None:
    """
    Transition an event to ``completed`` after its handlers succeed.

    Args:
        event_id: The event_id (primary key).
        handler_name: The subscriber(s) that processed the event.
        processing_time_ms: Handler execution time in milliseconds.
        db: Active database session.

    Returns:
        None.
    """
    db.execute(
        update(EventLog)
        .where(EventLog.id == event_id)
        .values(
            status=_STATUS_COMPLETED,
            handler_name=handler_name,
            processing_time_ms=processing_time_ms,
            completed_at=func.now(),
        )
    )
    db.commit()


def mark_failed(
    event_id: str,
    handler_name: str | None,
    error_message: str,
    processing_time_ms: int,
    db: Session,
) -> None:
    """
    Transition an event to ``failed`` when a handler raises.

    Args:
        event_id: The event_id (primary key).
        handler_name: The subscriber(s) that processed the event.
        error_message: The failure reason (truncated for storage).
        processing_time_ms: Handler execution time in milliseconds.
        db: Active database session.

    Returns:
        None.
    """
    db.execute(
        update(EventLog)
        .where(EventLog.id == event_id)
        .values(
            status=_STATUS_FAILED,
            handler_name=handler_name,
            error_message=error_message[:_MAX_ERROR_LEN],
            processing_time_ms=processing_time_ms,
            completed_at=func.now(),
        )
    )
    db.commit()


def get_event_log_summary(
    db: Session,
    *,
    hours: int = 24,
    failure_limit: int = 20,
) -> event_log_schema.EventLogSummary:
    """
    Aggregate the event_log into the admin-dashboard payload.

    Args:
        db: Active database session.
        hours: Look-back window for throughput/outcome/latency stats.
        failure_limit: Maximum number of recent failures to return.

    Returns:
        The aggregated dashboard summary.
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=hours)
    by_type = _summarize_by_type(db, window_start)
    return event_log_schema.EventLogSummary(
        window_hours=hours,
        total_events=sum(stats.total for stats in by_type),
        by_type=by_type,
        pending=_summarize_pending(db, now),
        recent_failures=_recent_failures(db, failure_limit),
    )


def _summarize_by_type(db: Session, window_start: datetime) -> list[event_log_schema.EventTypeStats]:
    """
    Build per-event-type status counts and latency for the window.

    Args:
        db: Active database session.
        window_start: Only events created at/after this instant are counted.

    Returns:
        Per-event-type statistics, ordered by event type.
    """
    status_counts = db.execute(
        select(EventLog.event_type, EventLog.status, func.count())
        .where(EventLog.created_at >= window_start)
        .group_by(EventLog.event_type, EventLog.status)
    ).all()
    latency_rows = db.execute(
        select(
            EventLog.event_type,
            func.avg(EventLog.processing_time_ms),
            func.max(EventLog.processing_time_ms),
        )
        .where(EventLog.created_at >= window_start, EventLog.processing_time_ms.is_not(None))
        .group_by(EventLog.event_type)
    ).all()
    latency_by_type = {event_type: (avg, maximum) for event_type, avg, maximum in latency_rows}

    counts_by_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for event_type, status, count in status_counts:
        counts_by_type[event_type][status] += count

    stats: list[event_log_schema.EventTypeStats] = []
    for event_type in sorted(counts_by_type):
        statuses = counts_by_type[event_type]
        avg, maximum = latency_by_type.get(event_type, (None, None))
        stats.append(
            event_log_schema.EventTypeStats(
                event_type=event_type,
                total=sum(statuses.values()),
                published=statuses.get(_STATUS_PUBLISHED, 0),
                queued=statuses.get(_STATUS_QUEUED, 0),
                processing=statuses.get(_STATUS_PROCESSING, 0),
                completed=statuses.get(_STATUS_COMPLETED, 0),
                failed=statuses.get(_STATUS_FAILED, 0),
                dead_letter=statuses.get(_STATUS_DEAD_LETTER, 0),
                avg_processing_time_ms=float(avg) if avg is not None else None,
                max_processing_time_ms=int(maximum) if maximum is not None else None,
            )
        )
    return stats


def _summarize_pending(db: Session, now: datetime) -> list[event_log_schema.EventLogPending]:
    """
    Group not-yet-finished events and compute each group's oldest age.

    Args:
        db: Active database session.
        now: Reference instant for the age computation.

    Returns:
        Pending groups, ordered oldest-first.
    """
    rows = db.execute(
        select(EventLog.event_type, EventLog.status, func.count(), func.min(EventLog.created_at))
        .where(EventLog.status.in_((_STATUS_PUBLISHED, _STATUS_PROCESSING)))
        .group_by(EventLog.event_type, EventLog.status)
    ).all()
    pending = [
        event_log_schema.EventLogPending(
            event_type=event_type,
            status=status,
            count=count,
            oldest_seconds=_age_seconds(oldest, now),
        )
        for event_type, status, count, oldest in rows
    ]
    pending.sort(key=lambda group: group.oldest_seconds or 0.0, reverse=True)
    return pending


def _recent_failures(db: Session, limit: int) -> list[event_log_schema.EventLogFailure]:
    """
    Fetch the most recent failed/dead-lettered events.

    Args:
        db: Active database session.
        limit: Maximum number of rows to return.

    Returns:
        Recent failures, newest first.
    """
    rows = (
        db.execute(
            select(EventLog)
            .where(EventLog.status.in_((_STATUS_FAILED, _STATUS_DEAD_LETTER)))
            .order_by(EventLog.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [event_log_schema.EventLogFailure.model_validate(row) for row in rows]


def _age_seconds(moment: datetime | None, now: datetime) -> float | None:
    """
    Compute the age in seconds of ``moment`` relative to ``now``.

    Args:
        moment: The earlier instant (may be timezone-naive from SQLite).
        now: The reference instant (timezone-aware, UTC).

    Returns:
        Age in seconds, or None when ``moment`` is None.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (now - moment).total_seconds()
