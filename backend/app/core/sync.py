"""Shared pieces of incremental sync: finding what changed and remembering what was deleted.

A client that keeps a local copy asks ``GET /sync`` what changed since its cursor. A record that still exists is
found by its ``updated_at``; a record that was deleted leaves a tombstone, a small row naming it, written in the
same transaction as the delete so a deletion is never lost. Each owning module keeps its own tombstone table built
on :class:`TombstoneMixin`, its records carry :class:`UpdatedAtMixin`, and it pages both through the helpers
here, in ``(stamp, id)`` order.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, DateTime, ForeignKey, delete, func, insert, select, tuple_
from sqlalchemy.orm import InstrumentedAttribute, Mapped, Session, mapped_column

#: How long a tombstone is kept. A cursor older than this may have missed a pruned deletion, so ``GET /sync``
#: refuses it and the client downloads everything again.
TOMBSTONE_RETENTION = timedelta(days=90)

#: A position in a ``(stamp, id)`` keyset walk: the stamp and id of the last row a page returned.
type Position = tuple[datetime, uuid.UUID]


class UpdatedAtMixin:
    """The ``updated_at`` column of a record a client syncs.

    Stamped by the database on insert and on every update, through the ORM or a Core ``UPDATE``, including a
    change the server derives (a thumbnail, a geocoded place). It says "what you read changed", where ``version``
    says "what you may edit changed".

    Attributes:
        updated_at: When the record last changed.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="When the record last changed",
    )


class TombstoneMixin:
    """The columns of a table that records deleted records of one owner.

    Attributes:
        id: The tombstone's own id, the tiebreak of its keyset order.
        user_id: The owner of the deleted record.
        deleted_at: When the record was deleted.

    Each tombstone model declares its own ``record_id``, typed as the id of the record it names.
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="Owner of the deleted record"
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, comment="When the record was deleted"
    )


@dataclass(frozen=True)
class Deletion:
    """A deleted record, as a module hands it to ``GET /sync``.

    Attributes:
        type: The sync type of the record, e.g. ``activity``.
        record_id: The id the record had.
        deleted_at: When it was deleted.
        position: The tombstone's place in its table's keyset order; ids are UUIDs.
    """

    type: str
    record_id: uuid.UUID
    deleted_at: datetime
    position: Position


def record_deletions(
    db: Session, model: type[TombstoneMixin], user_id: uuid.UUID, record_ids: Sequence[uuid.UUID], **columns: Any
) -> None:
    """Stage a tombstone for each deleted record, in the transaction that deletes them.

    Args:
        db: The session of the delete.
        model: The owning module's tombstone table.
        user_id: The owner of the records.
        record_ids: The ids of the deleted records.
        **columns: Further columns the table has, such as the record type of a shared table.
    """
    if record_ids:
        db.execute(insert(model), [{"user_id": user_id, "record_id": record_id, **columns} for record_id in record_ids])


def _after(
    stamp: InstrumentedAttribute[datetime],
    row_id: InstrumentedAttribute[uuid.UUID],
    after: Position | None,
    until: datetime,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [stamp < until]
    if after is not None:
        conditions.append(tuple_(stamp, row_id) > after)
    return conditions


def changed_rows[RowT: UpdatedAtMixin](
    db: Session,
    model: type[RowT],
    owner: InstrumentedAttribute[uuid.UUID],
    row_id: InstrumentedAttribute[uuid.UUID],
    user_id: uuid.UUID,
    after: Position | None,
    until: datetime,
    limit: int,
    conditions: Sequence[ColumnElement[bool]] = (),
) -> list[RowT]:
    """Read a user's rows changed after a position, oldest change first.

    Args:
        db: Database session.
        model: An ORM model carrying :class:`UpdatedAtMixin`.
        owner: The model's owner column, e.g. ``Gear.user_id``.
        row_id: The model's id column, the tiebreak of the order.
        user_id: The owner.
        after: Return rows strictly after this ``(updated_at, id)``; None from the first.
        until: Return only rows changed before this instant.
        limit: The most rows to return.
        conditions: Further conditions a row must meet.

    Returns:
        The rows, in ``(updated_at, id)`` order.
    """
    stmt = (
        select(model)
        .where(owner == user_id, *_after(model.updated_at, row_id, after, until), *conditions)
        .order_by(model.updated_at, row_id)
        .limit(limit)
    )
    return list(db.scalars(stmt))


def deleted_rows[TombstoneT: TombstoneMixin](
    db: Session,
    model: type[TombstoneT],
    user_id: uuid.UUID,
    after: Position | None,
    until: datetime,
    limit: int,
    conditions: Sequence[ColumnElement[bool]] = (),
) -> list[TombstoneT]:
    """Read a user's tombstones after a position, oldest deletion first.

    Args:
        db: Database session.
        model: The tombstone table.
        user_id: The owner.
        after: Return tombstones strictly after this ``(deleted_at, id)``; None from the first.
        until: Return only deletions before this instant.
        limit: The most tombstones to return.
        conditions: Further conditions a tombstone must meet.

    Returns:
        The tombstones, in ``(deleted_at, id)`` order.
    """
    stmt = (
        select(model)
        .where(model.user_id == user_id, *_after(model.deleted_at, model.id, after, until), *conditions)
        .order_by(model.deleted_at, model.id)
        .limit(limit)
    )
    return list(db.scalars(stmt))


def prune_tombstones(db: Session, model: type[TombstoneMixin], before: datetime) -> int:
    """Delete the tombstones older than an instant.

    Args:
        db: Database session; the caller commits.
        model: The tombstone table.
        before: Tombstones of deletions before this instant are removed.

    Returns:
        How many were removed.
    """
    result = db.execute(delete(model).where(model.deleted_at < before))
    return int(getattr(result, "rowcount", 0) or 0)
