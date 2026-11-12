"""SQL building blocks of the UUID conversion revisions.

Revisions import this module and never the app's models. The SQL of a function a released revision uses is frozen:
change behaviour with a new function, not by editing one. The module sits beside the migration runner rather than
under ``alembic/`` because every conversion revision shares it. PostgreSQL only: ``gen_random_uuid()`` is built in
from PostgreSQL 13. Table and index names come only from the literal spec of a revision, never from input. The helpers that rewrite stored ids and record the mapping run
while the parent still holds both its ``id`` and its ``new_id``.

Helpers added for the activity tables:

* :func:`add_uuid_ids_with_child_tables` maps the references and gives every child row its ``new_id`` in one rewrite.
* :func:`swap_in_uuid_primary_key` is the swap half of :func:`give_uuid_primary_key`, for a table whose ``new_id``
  is already filled.
* :func:`rewrite_json_array_ids` rewrites the integer elements of a JSON array column.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import aggregate_order_by

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


def swap_in_uuid_primary_key(table: str, indexes: Sequence[IdIndex] = ()) -> None:
    """Replace a table's integer ``id`` by its already filled ``new_id`` as the UUID primary key.

    Dropping the old column drops the primary key, every index that contains it and its serial sequence. Nothing
    references these ids. No server default stays on the column: the models generate the UUID in Python.

    Args:
        table: The table to convert; it must have its integer ``id`` and a filled ``new_id``.
        indexes: The indexes that contained ``id``, recreated on the new column.
    """
    op.drop_column(table, "id")
    op.alter_column(table, "new_id", new_column_name="id")
    op.alter_column(table, "id", existing_type=sa.Uuid(), nullable=False)
    op.create_primary_key(f"{table}_pkey", table, ["id"])
    for index in indexes:
        op.create_index(index.name, table, list(index.columns))


@dataclass(frozen=True)
class IdReference:
    """A column that holds the ``id`` of a table being converted.

    Attributes:
        table: The table holding the reference.
        column: The referencing column.
        nullable: Whether the column accepts ``NULL``.
        ondelete: The ``ON DELETE`` action of the foreign key.
        comment: The column comment, equal to the model's.
        indexes: The indexes that contain the column, recreated after the swap.
        unique_constraints: The unique constraints that contain the column, recreated after the swap.
    """

    table: str
    column: str
    nullable: bool
    ondelete: str
    comment: str
    indexes: tuple[IdIndex, ...] = ()
    unique_constraints: tuple[IdIndex, ...] = ()


#: The substrate tables that store event payloads, as (names the table has had, payload column, metadata column).
#: JASIL renames the unprefixed tables at startup, so an upgrade from v0.20 finds the old names and a development
#: database the prefixed ones.
_EVENT_TABLES: tuple[tuple[tuple[str, str], str, str], ...] = (
    (("jasil_event_outbox", "event_outbox"), "payload", "event_metadata"),
    (("jasil_processing_jobs", "processing_jobs"), "payload", "job_metadata"),
    (("jasil_event_log", "event_log"), "event_payload", "event_metadata"),
)


def _is_number(document: sa.ColumnElement[Any], key: str) -> sa.ColumnElement[bool]:
    """Match the documents that hold a JSON number under ``key``; ``NULL`` and strings do not match."""
    return sa.func.jsonb_typeof(document[key]) == "number"


def _integer_id(value_text: sa.ColumnElement[Any]) -> sa.ColumnElement[Any]:
    """Return the text of a JSON number as an ``integer``, or ``NULL`` when it is not a plain id.

    Comparing ``integer`` to ``numeric`` keeps PostgreSQL from using a primary key, so the lookup casts to the
    column's own type. Only whole numbers of up to nine digits match; anything else names no row.
    """
    return sa.case((value_text.regexp_match("^[0-9]{1,9}$").is_not(None), sa.cast(value_text, sa.Integer)))


def _with_uuid_id(
    document: sa.ColumnElement[Any], key: str, parent: sa.TableClause, by_primary_key: bool = False
) -> sa.ColumnElement[Any]:
    """Return the jsonb document with the integer under ``key`` replaced by the UUID of its parent row, as a string.

    An id that matches no parent row (a dangling reference) gets a fresh random UUID, so the value is still a valid
    id that names nothing.

    Args:
        document: The jsonb document.
        key: The key that holds the id.
        parent: The parent table, with its ``id`` and ``new_id``.
        by_primary_key: Look the parent up with an ``integer`` comparison, so a large parent table is read through its
            primary key instead of being scanned once per rewritten row.
    """
    value = document[key].astext
    matches = parent.c.id == (_integer_id(value) if by_primary_key else sa.cast(value, sa.Numeric))
    new_id = sa.func.coalesce(
        sa.select(parent.c.new_id).where(matches).scalar_subquery(),
        sa.func.gen_random_uuid(),
    )
    return sa.func.jsonb_set(
        document, postgresql.array([key], type_=sa.Text), sa.func.to_jsonb(sa.cast(new_id, sa.Text))
    )


def _existing_tables(names: Sequence[str]) -> list[str]:
    """Return the names of the tables that exist, in the given order."""
    connection = op.get_bind()
    return [
        name
        for name in names
        if connection.execute(sa.text("SELECT to_regclass(:name)"), {"name": name}).scalar() is not None
    ]


def add_uuid_ids_with_references(parent: str, references: Sequence[IdReference]) -> None:
    """Give a table a random ``new_id`` and map every reference to it, keeping the integer ids.

    Nothing is dropped, so the stored ids can still be rewritten from the integer ids before
    :func:`swap_in_uuid_ids` replaces them.

    Args:
        parent: The table being converted; it must still have its integer ``id``.
        references: The columns that hold its ids.
    """
    parent_rows = sa.table(parent, sa.column("id"), sa.column("new_id"))
    op.add_column(parent, sa.Column("new_id", sa.Uuid(), nullable=True))
    op.execute(sa.update(parent_rows).values(new_id=sa.func.gen_random_uuid()))
    for reference in references:
        new_column = f"new_{reference.column}"
        child = sa.table(reference.table, sa.column(reference.column), sa.column(new_column))
        op.add_column(reference.table, sa.Column(new_column, sa.Uuid(), nullable=True))
        op.execute(
            sa.update(child)
            .values({new_column: parent_rows.c.new_id})
            .where(parent_rows.c.id == child.c[reference.column])
        )


def add_uuid_ids_with_child_tables(parent: str, children: Sequence[IdReference]) -> None:
    """Give a table and each child table random ``new_id`` values and map every child's reference, in one rewrite each.

    Each child row gets its own ``new_id`` and its ``new_<column>`` in a single ``UPDATE``, so the heap of a large
    child table is rewritten once. A ``NULL`` reference stays ``NULL``. Nothing is dropped: the stored ids can still be
    rewritten from the integer ids before :func:`swap_in_uuid_ids` and :func:`swap_in_uuid_primary_key` replace them.

    Args:
        parent: The table being converted; it must still have its integer ``id``.
        children: The columns that hold its ids, one per child table; each child must still have its integer ``id``.
    """
    parent_rows = sa.table(parent, sa.column("id"), sa.column("new_id"))
    op.add_column(parent, sa.Column("new_id", sa.Uuid(), nullable=True))
    op.execute(sa.update(parent_rows).values(new_id=sa.func.gen_random_uuid()))
    for child in children:
        new_column = f"new_{child.column}"
        rows = sa.table(child.table, sa.column(child.column), sa.column("new_id"), sa.column(new_column))
        op.add_column(child.table, sa.Column("new_id", sa.Uuid(), nullable=True))
        op.add_column(child.table, sa.Column(new_column, sa.Uuid(), nullable=True))
        parent_id = sa.select(parent_rows.c.new_id).where(parent_rows.c.id == rows.c[child.column]).scalar_subquery()
        op.execute(sa.update(rows).values({"new_id": sa.func.gen_random_uuid(), new_column: parent_id}))


def rewrite_payload_ids(event_types: Sequence[str], key: str, parent: str, by_primary_key: bool = False) -> None:
    """Rewrite an integer id in the payloads of the given event types to the UUID of its parent row.

    Every row of every present event table is rewritten whatever its status (pending, retrying, claimed, dead
    letter, completed, relayed or not). An id that matches no parent row becomes a fresh random UUID.

    Args:
        event_types: The event types whose payloads carry the id under ``key``.
        key: The payload key that holds the id.
        parent: The table whose ids the key holds; it must still have its ``new_id``.
        by_primary_key: Look the parent up through its primary key (see :func:`_with_uuid_id`).
    """
    parents = sa.table(parent, sa.column("id"), sa.column("new_id"))
    for names, payload_column, _metadata_column in _EVENT_TABLES:
        for table in _existing_tables(names):
            rows = sa.table(table, sa.column(payload_column, postgresql.JSONB), sa.column("event_type"))
            document = rows.c[payload_column]
            op.execute(
                sa.update(rows)
                .values({payload_column: _with_uuid_id(document, key, parents, by_primary_key)})
                .where(rows.c.event_type.in_(list(event_types)), _is_number(document, key))
            )


def rewrite_metadata_ids(key: str, parent: str, by_primary_key: bool = False) -> None:
    """Rewrite an integer id under ``key`` in the metadata of every event row to the UUID of its parent row.

    Rows are matched by the presence of a numeric value under the key, whatever their event type.

    Args:
        key: The metadata key that holds the id.
        parent: The table whose ids the key holds; it must still have its ``new_id``.
        by_primary_key: Look the parent up through its primary key (see :func:`_with_uuid_id`).
    """
    parents = sa.table(parent, sa.column("id"), sa.column("new_id"))
    for names, _payload_column, metadata_column in _EVENT_TABLES:
        for table in _existing_tables(names):
            rows = sa.table(table, sa.column(metadata_column, postgresql.JSONB))
            document = rows.c[metadata_column]
            op.execute(
                sa.update(rows)
                .values({metadata_column: _with_uuid_id(document, key, parents, by_primary_key)})
                .where(_is_number(document, key))
            )


def rewrite_notification_option_ids(key: str, parent: str, by_primary_key: bool = False) -> None:
    """Rewrite an integer id under ``key`` in the notification options to the UUID of its parent row.

    The other keys of the options are kept.

    Args:
        key: The options key that holds the id.
        parent: The table whose ids the key holds; it must still have its ``new_id``.
        by_primary_key: Look the parent up through its primary key (see :func:`_with_uuid_id`).
    """
    parents = sa.table(parent, sa.column("id"), sa.column("new_id"))
    rows = sa.table("notifications", sa.column("options", sa.JSON))
    document = sa.cast(rows.c.options, postgresql.JSONB)
    op.execute(
        sa.update(rows)
        .values(options=sa.cast(_with_uuid_id(document, key, parents, by_primary_key), sa.JSON))
        .where(rows.c.options.is_not(None), _is_number(document, key))
    )


def rewrite_json_array_ids(table: str, column: str, parent: str) -> None:
    """Rewrite the integer elements of a JSON array column to the UUID strings of their parent rows.

    An element that matches no parent row becomes a fresh random UUID, as in the payload rewrites. String and ``null``
    elements and the order of the elements are kept. ``NULL`` columns, empty arrays, arrays without a number and
    values that are not arrays are not touched.

    The column type is ``JSON`` with a ``JSONB`` variant on PostgreSQL; this helper declares it as ``JSONB``, the type
    the database holds, so the column must be ``jsonb``.

    Args:
        table: The table that holds the array column.
        column: The array column.
        parent: The table whose ids the elements hold; it must still have its ``new_id``.
    """
    parents = sa.table(parent, sa.column("id"), sa.column("new_id"))
    rows = sa.table(table, sa.column(column, postgresql.JSONB))
    document = rows.c[column]
    elements = (
        sa.func.jsonb_array_elements(document)
        .table_valued(sa.column("value", postgresql.JSONB), with_ordinality="ordinality")
        .render_derived(name="elements")
    )
    is_number = sa.func.jsonb_typeof(elements.c.value) == "number"
    new_id = sa.func.coalesce(
        sa.select(parents.c.new_id)
        .where(parents.c.id == _integer_id(sa.cast(elements.c.value, sa.Text)))
        .scalar_subquery(),
        sa.func.gen_random_uuid(),
    )
    rewritten = sa.case((is_number, sa.func.to_jsonb(sa.cast(new_id, sa.Text))), else_=elements.c.value)
    values = (
        sa.select(sa.func.jsonb_agg(aggregate_order_by(rewritten, elements.c.ordinality), type_=postgresql.JSONB))
        .select_from(elements)
        .scalar_subquery()
    )
    has_number = sa.exists(sa.select(1).select_from(elements).where(is_number))
    op.execute(sa.update(rows).values({column: values}).where(sa.func.jsonb_typeof(document) == "array", has_number))


def record_old_ids(parent: str) -> None:
    """Record the old and new id of every row of a table in ``uuid_migration_ids``.

    Data migration 13 reads the table to rename the stored files named by an integer id, then drops it. The table
    is created when it does not exist yet.

    Args:
        parent: The table being converted; it must still have its ``id`` and ``new_id``.
    """
    op.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS uuid_migration_ids (table_name varchar(64) NOT NULL, "
            "old_id integer NOT NULL, new_id uuid NOT NULL, "
            "CONSTRAINT uuid_migration_ids_pkey PRIMARY KEY (table_name, old_id))"
        )
    )
    parents = sa.table(parent, sa.column("id"), sa.column("new_id"))
    recorded = sa.table("uuid_migration_ids", sa.column("table_name"), sa.column("old_id"), sa.column("new_id"))
    op.execute(
        sa.insert(recorded).from_select(
            ["table_name", "old_id", "new_id"], sa.select(sa.literal(parent), parents.c.id, parents.c.new_id)
        )
    )


def schedule_stored_key_renames() -> None:
    """Register data migration 13, which renames the stored files named by an integer id, as not executed."""
    op.execute(
        sa.text(
            "INSERT INTO migrations (id, name, description, executed) VALUES "
            "(13, 'v0.21.0', 'Rename the stored files named by an integer id to their UUID', false) "
            "ON CONFLICT (id) DO UPDATE SET executed = false"
        )
    )


def swap_in_uuid_ids(parent: str, parent_indexes: Sequence[IdIndex], references: Sequence[IdReference]) -> None:
    """Replace the integer ``id`` of a table and every column that references it by the ``new_id`` columns.

    Dropping a column drops its foreign key, its indexes and the unique constraints that contain it, and dropping the
    parent's ``id`` drops its primary key, its serial sequence and its indexes. All of them are recreated on the UUID
    columns with the same names. No server default stays: the models generate the UUID in Python.

    Args:
        parent: The table being converted.
        parent_indexes: The indexes that contained the parent's ``id``.
        references: The columns that hold its ids, each with the indexes and unique constraints to recreate.
    """
    for reference in references:
        op.drop_column(reference.table, reference.column)
        op.alter_column(reference.table, f"new_{reference.column}", new_column_name=reference.column)
        op.alter_column(
            reference.table,
            reference.column,
            existing_type=sa.Uuid(),
            nullable=reference.nullable,
            comment=reference.comment,
        )
    op.drop_column(parent, "id")
    op.alter_column(parent, "new_id", new_column_name="id")
    op.alter_column(parent, "id", existing_type=sa.Uuid(), nullable=False)
    op.create_primary_key(f"{parent}_pkey", parent, ["id"])
    for index in parent_indexes:
        op.create_index(index.name, parent, list(index.columns))
    for reference in references:
        op.create_foreign_key(
            f"{reference.table}_{reference.column}_fkey",
            reference.table,
            parent,
            [reference.column],
            ["id"],
            ondelete=reference.ondelete,
        )
        for index in reference.indexes:
            op.create_index(index.name, reference.table, list(index.columns))
        for constraint in reference.unique_constraints:
            op.create_unique_constraint(constraint.name, reference.table, list(constraint.columns))
