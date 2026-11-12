"""The jsonb rewrite helpers of ``migrations.uuid_conversion`` that no revision calls yet, on scratch tables."""

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine

from migrations import uuid_conversion

_TABLES = (
    ("event_outbox", "event_metadata"),
    ("jasil_processing_jobs", "job_metadata"),
    ("jasil_event_log", "event_metadata"),
)
_PARENT_NEW_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _prepare(engine: Engine) -> None:
    """Create a parent with one row and the three event tables, under both the old and the prefixed names."""
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE scratch_parent (id integer PRIMARY KEY, new_id uuid)"))
        connection.execute(
            sa.text("INSERT INTO scratch_parent VALUES (1, CAST(:new_id AS uuid))"), {"new_id": _PARENT_NEW_ID}
        )
        connection.execute(sa.text("CREATE TABLE event_outbox (id varchar PRIMARY KEY, event_metadata jsonb)"))
        connection.execute(sa.text("CREATE TABLE jasil_processing_jobs (id varchar PRIMARY KEY, job_metadata jsonb)"))
        connection.execute(sa.text("CREATE TABLE jasil_event_log (id varchar PRIMARY KEY, event_metadata jsonb)"))
        documents = {
            "number": {"scratch_id": 1, "user_id": 7},
            "dangling": {"scratch_id": 99},
            "string": {"scratch_id": "kept"},
            "null": {"scratch_id": None},
            "absent": {"user_id": 7},
            "no-metadata": None,
        }
        for table, column in _TABLES:
            rows = sa.table(table, sa.column("id"), sa.column(column, postgresql.JSONB(none_as_null=True)))
            connection.execute(sa.insert(rows), [{"id": row_id, column: doc} for row_id, doc in documents.items()])


def test_rewrite_metadata_ids_maps_numbers_in_every_present_event_table(upgrade_db):
    _prepare(upgrade_db)

    with upgrade_db.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        uuid_conversion.rewrite_metadata_ids("scratch_id", "scratch_parent")

    for table, column in _TABLES:
        rows = sa.table(table, sa.column("id"), sa.column(column))
        with upgrade_db.connect() as connection:
            documents = dict(connection.execute(sa.select(rows.c.id, rows.c[column])).all())
        assert documents["number"] == {"scratch_id": _PARENT_NEW_ID, "user_id": 7}
        assert documents["string"] == {"scratch_id": "kept"}
        assert documents["null"] == {"scratch_id": None}
        assert documents["absent"] == {"user_id": 7}
        assert documents["no-metadata"] is None
        dangling = documents["dangling"]["scratch_id"]
        assert dangling != _PARENT_NEW_ID
        assert len(dangling) == 36
