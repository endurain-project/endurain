"""The helpers of ``migrations.uuid_conversion`` that revisions 89 and earlier do not call, on scratch tables."""

import uuid

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine

from migrations import uuid_conversion
from migrations.uuid_conversion import IdIndex, IdReference

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


def _in_migration(engine: Engine, helper, *args) -> None:
    """Run a helper the way a revision does, inside an Alembic operations context."""
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        helper(*args)


def test_add_uuid_ids_with_child_tables_keeps_a_null_reference_null_and_gives_every_row_an_id(upgrade_db):
    with upgrade_db.begin() as connection:
        connection.execute(sa.text("CREATE TABLE scratch_parent (id integer PRIMARY KEY)"))
        connection.execute(sa.text("CREATE TABLE scratch_child (id integer PRIMARY KEY, parent_id integer)"))
        connection.execute(sa.text("INSERT INTO scratch_parent VALUES (1), (2)"))
        connection.execute(sa.text("INSERT INTO scratch_child VALUES (1, 1), (2, NULL), (3, 1), (4, 2)"))
    child = IdReference("scratch_child", "parent_id", nullable=True, ondelete="CASCADE", comment="Parent")

    _in_migration(upgrade_db, uuid_conversion.add_uuid_ids_with_child_tables, "scratch_parent", (child,))

    with upgrade_db.connect() as connection:
        parents = dict(connection.execute(sa.text("SELECT id, new_id FROM scratch_parent")).all())
        rows = {
            row.id: row
            for row in connection.execute(sa.text("SELECT id, parent_id, new_id, new_parent_id FROM scratch_child"))
        }
        defaults = (
            connection.execute(
                sa.text(
                    "SELECT column_default FROM information_schema.columns "
                    "WHERE table_name = 'scratch_child' AND column_name IN ('new_id', 'new_parent_id')"
                )
            )
            .scalars()
            .all()
        )
    assert len(set(parents.values())) == 2 and None not in parents.values()
    assert {row.parent_id for row in rows.values()} == {1, None, 2}
    assert rows[1].new_parent_id == parents[1] == rows[3].new_parent_id
    assert rows[2].new_parent_id is None
    assert rows[4].new_parent_id == parents[2]
    assert len({row.new_id for row in rows.values()}) == 4 and None not in {row.new_id for row in rows.values()}
    assert defaults == [None, None]


def test_swap_in_uuid_primary_key_replaces_the_integer_id_with_the_filled_new_id(upgrade_db):
    with upgrade_db.begin() as connection:
        connection.execute(sa.text("CREATE TABLE scratch_rows (id serial PRIMARY KEY, name text, new_id uuid)"))
        connection.execute(sa.text("CREATE INDEX ix_scratch_rows_name_id ON scratch_rows (name, id)"))
        connection.execute(sa.text("INSERT INTO scratch_rows (name, new_id) VALUES ('a', gen_random_uuid())"))
        connection.execute(sa.text("INSERT INTO scratch_rows (name, new_id) VALUES ('b', gen_random_uuid())"))
        expected = dict(connection.execute(sa.text("SELECT name, new_id FROM scratch_rows")).all())

    _in_migration(
        upgrade_db,
        uuid_conversion.swap_in_uuid_primary_key,
        "scratch_rows",
        (IdIndex("ix_scratch_rows_name_id", ("name", "id")),),
    )

    inspector = sa.inspect(upgrade_db)
    columns = {column["name"]: column for column in inspector.get_columns("scratch_rows")}
    assert set(columns) == {"id", "name"}
    assert isinstance(columns["id"]["type"], sa.Uuid) and not columns["id"]["nullable"]
    assert columns["id"]["default"] is None
    primary_key = inspector.get_pk_constraint("scratch_rows")
    assert (primary_key["name"], primary_key["constrained_columns"]) == ("scratch_rows_pkey", ["id"])
    assert [index["column_names"] for index in inspector.get_indexes("scratch_rows")] == [["name", "id"]]
    with upgrade_db.connect() as connection:
        assert dict(connection.execute(sa.text("SELECT name, id FROM scratch_rows")).all()) == expected


def test_rewrite_json_array_ids_maps_number_elements_in_order(upgrade_db):
    with upgrade_db.begin() as connection:
        connection.execute(sa.text("CREATE TABLE scratch_parent (id integer PRIMARY KEY, new_id uuid)"))
        connection.execute(sa.text("CREATE TABLE scratch_jobs (id varchar PRIMARY KEY, ids jsonb)"))
        connection.execute(
            sa.text("INSERT INTO scratch_parent VALUES (1, CAST(:one AS uuid)), (2, CAST(:two AS uuid))"),
            {"one": _PARENT_NEW_ID, "two": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
        )
        documents = {
            "numbers": [2, 1, 99],
            "mixed": [1, "kept", None, 2],
            "strings": ["x", "y"],
            "empty": [],
            "object": {"a": 1},
            "scalar": 5,
            "null-value": None,
        }
        rows = sa.table("scratch_jobs", sa.column("id"), sa.column("ids", postgresql.JSONB(none_as_null=True)))
        connection.execute(sa.insert(rows), [{"id": key, "ids": document} for key, document in documents.items()])
        connection.execute(sa.text("INSERT INTO scratch_jobs VALUES ('sql-null', NULL)"))

    _in_migration(upgrade_db, uuid_conversion.rewrite_json_array_ids, "scratch_jobs", "ids", "scratch_parent")

    with upgrade_db.connect() as connection:
        found = dict(connection.execute(sa.text("SELECT id, ids FROM scratch_jobs")).all())
    two = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    assert found["numbers"][:2] == [two, _PARENT_NEW_ID]
    assert str(uuid.UUID(found["numbers"][2])) == found["numbers"][2]
    assert found["numbers"][2] not in (two, _PARENT_NEW_ID)
    assert found["mixed"] == [_PARENT_NEW_ID, "kept", None, two]
    assert found["strings"] == ["x", "y"]
    assert found["empty"] == []
    assert found["object"] == {"a": 1}
    assert found["scalar"] == 5
    assert found["null-value"] is None
    assert found["sql-null"] is None
