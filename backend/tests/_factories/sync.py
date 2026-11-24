"""Stamps and tombstones for the sync walk, which orders records by when they changed."""

import uuid
from collections.abc import Collection
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

import modules.health.models as health_models


def restamp(db: Session, model: type, record_ids: Collection[uuid.UUID], stamp: datetime) -> None:
    """Set when records last changed, as a bulk edit stamps many rows alike (flushed, not committed).

    Args:
        db: Database session.
        model: The record's model, which has ``id`` and ``updated_at``.
        record_ids: The records to stamp.
        stamp: The instant they changed.
    """
    db.execute(update(model).where(model.id.in_(record_ids)).values(updated_at=stamp))  # ty: ignore[unresolved-attribute]
    db.flush()


def make_health_tombstone(db: Session, user_id: uuid.UUID, record_type: str, deleted_at: datetime) -> uuid.UUID:
    """Stage the tombstone a deleted health record leaves (flushed, not committed).

    Args:
        db: Database session.
        user_id: The deleted record's owner.
        record_type: The record's sync type, e.g. ``health_weight``.
        deleted_at: When it was deleted.

    Returns:
        The id the deleted record had.
    """
    record_id = uuid.uuid4()
    db.add(
        health_models.HealthRecordDeletion(
            user_id=user_id, record_type=record_type, record_id=record_id, deleted_at=deleted_at
        )
    )
    db.flush()
    return record_id
