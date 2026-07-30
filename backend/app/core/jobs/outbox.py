"""CRUD for ``event_outbox`` — the durable-delivery staging table.

``add_to_outbox`` persists an event and commits it on the caller's session. Note
that the ingestion path commits per-CRUD, so this is *not* one transaction with
the domain change — the domain row is the source of truth and each subscriber's
reconciliation net (backfill/sweeper) recovers anything dropped by a crash
between the domain commit and the outbox write. ``list_unrelayed`` and
``mark_relayed`` are used by the relay; combined with the idempotent job fan-out
(dedup on ``event_id + subscriber_id``) and ``SELECT ... FOR UPDATE SKIP LOCKED``,
that makes concurrent relayers safe and re-relaying a row harmless.
"""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.jobs.models import EventOutbox
from core.platform.events import Event


def add_to_outbox(event: Event, *, now: datetime, db: Session) -> str:
    """
    Persist an event to the outbox and commit it on the caller's session.

    Best-effort durability: the write commits on ``db``, but because the
    ingestion path already committed the domain change in an earlier transaction,
    the two are not atomic. A crash between them can drop the event; the
    subscriber's reconciliation net is the safety net.

    Args:
        event: The event envelope to persist.
        now: Current instant (the outbox write time).
        db: Active database session (the producer's).

    Returns:
        The new outbox row id.
    """
    outbox_id = str(uuid.uuid4())
    db.add(
        EventOutbox(
            id=outbox_id,
            event_id=event.event_id,
            event_type=event.event_type,
            source=event.source,
            timestamp=event.timestamp,
            payload=event.payload,
            event_metadata=event.metadata or None,
            created_at=now,
        )
    )
    db.commit()
    return outbox_id


def list_unrelayed(*, limit: int, db: Session) -> list[EventOutbox]:
    """
    Fetch the oldest not-yet-relayed outbox rows, locking them for this relayer.

    On PostgreSQL the rows are claimed with ``FOR UPDATE SKIP LOCKED`` so
    concurrent relayers across replicas take disjoint batches (no single-runner
    lock needed); on SQLite the clause is omitted (tests are single-threaded).

    Args:
        limit: Maximum number of rows to return.
        db: Active database session.

    Returns:
        Unrelayed outbox rows, oldest-first.
    """
    stmt = select(EventOutbox).where(EventOutbox.relayed_at.is_(None)).order_by(EventOutbox.created_at).limit(limit)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)  # pragma: no cover - Postgres-only path
    return list(db.execute(stmt).scalars().all())


def mark_relayed(outbox_id: str, *, now: datetime, db: Session) -> None:
    """
    Stamp an outbox row as relayed.

    Args:
        outbox_id: The outbox row id.
        now: Current instant.
        db: Active database session.

    Returns:
        None.
    """
    db.execute(update(EventOutbox).where(EventOutbox.id == outbox_id).values(relayed_at=now))
    db.commit()
