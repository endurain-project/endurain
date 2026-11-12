"""SQL building blocks of the UUID conversion revisions.

Revisions import this module and never the app's models. The SQL of a function a released revision uses is frozen:
change behaviour with a new function, not by editing one. The module sits beside the migration runner rather than
under ``alembic/`` because every conversion revision shares it. PostgreSQL only: ``gen_random_uuid()`` is built in
from PostgreSQL 13. Table and index names come only from the literal spec of a revision, never from input.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

from alembic import op


@dataclass(frozen=True)
class IdIndex:
    """An index that contains ``id`` and must be recreated after the column is replaced.

    Attributes:
        name: The index name.
        columns: The indexed columns in order, ``id`` among them.
    """

    name: str
    columns: tuple[str, ...]


_MICROSECOND: sa.ColumnElement[Any] = sa.literal_column("interval '1 microsecond'")


def _id_rank(table: sa.TableClause, partition_by: sa.ColumnElement[Any] | None = None) -> sa.Subquery:
    """Rank the rows of a table by ``id``, restarting at 1 for each value of ``partition_by``."""
    rank = sa.func.row_number().over(partition_by=partition_by, order_by=table.c.id).label("rank")
    return sa.select(table.c.id, rank).subquery("ranked")


def add_created_at_in_id_order(table: str, comment: str) -> None:
    """Add a ``created_at`` column that records the order of the integer ids.

    Rows get the transaction start time plus their id rank in microseconds, so sorting by ``created_at`` keeps the
    old id order. New rows default to ``now()``.

    Args:
        table: The table to extend; it must still have its integer ``id``.
        comment: The column comment, equal to the model's.
    """
    rows = sa.table(table, sa.column("id"), sa.column("created_at"))
    ranked = _id_rank(rows)
    op.add_column(table, sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        sa.update(rows).values(created_at=sa.func.now() + ranked.c.rank * _MICROSECOND).where(rows.c.id == ranked.c.id)
    )
    op.alter_column(
        table,
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
        comment=comment,
    )


def keep_created_at_in_id_order(table: str) -> None:
    """Make ``created_at`` rise with the integer ids, changing as few values as possible.

    Walking the rows in id order, each ``created_at`` becomes the larger of its own value and the previous row's
    value plus one microsecond. Rows already in order keep their value, so only ties and rows whose ``created_at`` runs
    against their id move. ``updated_at`` is not touched.

    Args:
        table: The table with an integer ``id`` and a ``created_at`` column.
    """
    rows = sa.table(table, sa.column("id"), sa.column("created_at"))
    rank = sa.func.row_number().over(order_by=rows.c.id)
    offsets = sa.select(rows.c.id, rows.c.created_at, rank.label("rank")).subquery("offsets")
    slack = offsets.c.created_at - offsets.c.rank * _MICROSECOND
    floors = sa.select(
        offsets.c.id,
        offsets.c.rank,
        sa.func.max(slack).over(order_by=offsets.c.id).label("floor"),
    ).subquery("floors")
    op.execute(
        sa.update(rows).values(created_at=floors.c.floor + floors.c.rank * _MICROSECOND).where(rows.c.id == floors.c.id)
    )


def empty_tombstones(table: str) -> None:
    """Delete every row of a tombstone table and retype its ``record_id`` as ``uuid``.

    The ids the rows named are gone or about to change, so the rows cannot be mapped. The table is empty, so the
    ``NOT NULL`` constraint and the comment hold.

    Args:
        table: The tombstone table.
    """
    op.execute(sa.delete(sa.table(table)))
    op.alter_column(table, "record_id", existing_type=sa.Integer(), type_=sa.Uuid(), postgresql_using="NULL")


def give_uuid_primary_key(table: str, indexes: Sequence[IdIndex] = ()) -> None:
    """Replace a table's integer ``id`` with a random UUID primary key.

    Dropping the old column drops the primary key, every index that contains it and its serial sequence. Nothing
    references these ids. No server default stays on the column: the models generate the UUID in Python.

    Args:
        table: The table to convert.
        indexes: The indexes that contained ``id``, recreated on the new column.
    """
    op.add_column(table, sa.Column("new_id", sa.Uuid(), nullable=True))
    op.execute(sa.update(sa.table(table, sa.column("new_id"))).values(new_id=sa.func.gen_random_uuid()))
    op.drop_column(table, "id")
    op.alter_column(table, "new_id", new_column_name="id")
    op.create_primary_key(f"{table}_pkey", table, ["id"])
    for index in indexes:
        op.create_index(index.name, table, list(index.columns))
