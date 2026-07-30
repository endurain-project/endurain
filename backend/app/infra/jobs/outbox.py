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

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from infra.events import Event
from infra.jobs.models import EventOutbox


def add_to_outbox(event: Event, *, now: datetime, db: Session, commit: bool = True) -> str:
    """
    Persist an event to the outbox on the caller's session.

    With ``commit=True`` (default) the write is committed immediately. Callers on
    the ingestion path pass ``commit=False`` so the outbox row is only flushed and
    joins their open transaction — the domain change and the outbox row then commit
    together (atomic delivery; see :func:`infra.publisher.publish_committing`).
    When committed independently (the historical best-effort seam), the outbox
    write is *not* atomic with the domain change, so a crash between them can drop
    the event and the subscriber's reconciliation net is the safety net.

    Args:
        event: The event envelope to persist.
        now: Current instant (the outbox write time).
        db: Active database session (the producer's).
        commit: When True, commit immediately; when False, flush only and leave the
            row in the caller's open transaction.

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
    if commit:
        db.commit()
    else:
        db.flush()
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


# Rows deleted per batch when pruning; bounded so each delete transaction stays
# short and never blocks the relay for long.
_PRUNE_BATCH_SIZE = 1000
_PRUNE_MAX_BATCHES = 10_000


def delete_relayed_before(cutoff: datetime, *, db: Session, batch_size: int = _PRUNE_BATCH_SIZE) -> int:
    """
    Delete relayed outbox rows older than ``cutoff``, in bounded batches.

    Only rows that have been relayed (``relayed_at`` set) and whose relay is older
    than ``cutoff`` are removed; unrelayed rows are pending work and are never
    touched. A relayed row's only remaining value is audit — the per-subscriber
    jobs it fanned out into are the source of truth — so it is safe to prune.

    Args:
        cutoff: Delete rows whose ``relayed_at`` is strictly before this instant.
        db: Active database session.
        batch_size: Maximum rows deleted per batch.

    Returns:
        The total number of rows deleted.
    """
    total = 0
    for _ in range(_PRUNE_MAX_BATCHES):
        id_stmt = (
            select(EventOutbox.id)
            .where(EventOutbox.relayed_at.is_not(None), EventOutbox.relayed_at < cutoff)
            .limit(batch_size)
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            id_stmt = id_stmt.with_for_update(skip_locked=True)  # pragma: no cover - Postgres-only path
        ids = list(db.execute(id_stmt).scalars().all())
        if not ids:
            break
        db.execute(delete(EventOutbox).where(EventOutbox.id.in_(ids)))
        db.commit()
        total += len(ids)
        if len(ids) < batch_size:
            break
    return total
