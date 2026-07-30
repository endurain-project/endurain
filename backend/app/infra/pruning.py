"""Bounded batch deletes shared by the substrate's prunable tables.

Every table :mod:`infra.retention` prunes (``event_log``, relayed
``event_outbox`` rows, ``completed`` ``processing_jobs``) is deleted the
same way, and only the model and the filter differ. The batching is what
keeps each delete transaction short, so a prune pass never holds locks on
a hot table long enough to block the relay or the worker.
"""

from typing import Any

from sqlalchemy import ColumnExpressionArgument, delete, select
from sqlalchemy.orm import Session

# Rows deleted per batch when pruning; bounded so each delete transaction
# stays short.
PRUNE_BATCH_SIZE = 1000
# Safety cap on batches per pass so a pathological backlog cannot spin
# forever; the next scheduled pass continues where this one left off.
PRUNE_MAX_BATCHES = 10_000


def bounded_delete(
    model: type[Any],
    *conditions: ColumnExpressionArgument[bool],
    db: Session,
    batch_size: int = PRUNE_BATCH_SIZE,
) -> int:
    """
    Delete the rows matching ``conditions`` in bounded, committed batches.

    Args:
        model: Mapped class to delete from; must expose an ``id`` column.
        *conditions: Filters selecting the rows that are safe to prune.
        db: Active database session.
        batch_size: Maximum rows deleted per batch.

    Returns:
        The total number of rows deleted.
    """
    total = 0
    for _ in range(PRUNE_MAX_BATCHES):
        id_stmt = select(model.id).where(*conditions).limit(batch_size)
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            # Concurrent prunes step over each other's claimed page rather
            # than blocking on it.
            id_stmt = id_stmt.with_for_update(skip_locked=True)  # pragma: no cover - Postgres-only path
        ids = list(db.execute(id_stmt).scalars().all())
        if not ids:
            break
        db.execute(delete(model).where(model.id.in_(ids)))
        db.commit()
        total += len(ids)
        if len(ids) < batch_size:
            break
    return total
