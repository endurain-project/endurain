"""Tests for the migration that makes the one-time token hashes unique (76)."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/76_token_hash_unique.py"
_TABLES = ("password_reset_tokens", "sign_up_tokens")


def _migration_module():
    spec = importlib.util.spec_from_file_location("token_hash_unique", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table(name: str) -> sa.TableClause:
    return sa.table(name, sa.column("id"), sa.column("token_hash"), sa.column("created_at"))


def _engine_with(rows: list[tuple[str, str, str]]) -> sa.Engine:
    """Create both tables holding the same ``(id, token_hash, created_at)`` rows."""
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for table in _TABLES:
            connection.execute(
                sa.text(f"CREATE TABLE {table} (id VARCHAR(64) PRIMARY KEY, token_hash VARCHAR(128), created_at TEXT)")
            )
            for row_id, token_hash, created_at in rows:
                connection.execute(
                    _table(table).insert().values(id=row_id, token_hash=token_hash, created_at=created_at)
                )
    return engine


def _run(engine: sa.Engine, step: str) -> None:
    migration = _migration_module()
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        getattr(migration, step)()


def _unique_index_names(engine: sa.Engine, table: str) -> list[str]:
    return [index["name"] for index in sa.inspect(engine).get_indexes(table) if index["unique"]]


def test_it_chains_onto_the_session_app_redirect_uri_revision():
    migration = _migration_module()

    assert migration.down_revision == "e75c9a3d7b24"


def test_the_upgrade_creates_the_unique_indexes_and_the_downgrade_drops_them():
    engine = _engine_with([("a", "h1", "2026-01-01")])

    _run(engine, "upgrade")
    for table in _TABLES:
        assert _unique_index_names(engine, table) == [f"ix_{table}_token_hash"]
    _run(engine, "downgrade")

    for table in _TABLES:
        assert _unique_index_names(engine, table) == []


@pytest.mark.parametrize("table", _TABLES)
def test_the_index_refuses_a_second_row_with_the_same_hash(table: str):
    engine = _engine_with([("a", "h1", "2026-01-01")])
    _run(engine, "upgrade")

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(_table(table).insert().values(id="b", token_hash="h1", created_at="x"))


@pytest.mark.parametrize("table", _TABLES)
def test_the_upgrade_keeps_the_earliest_row_of_each_duplicated_hash(table: str):
    engine = _engine_with(
        [
            ("c", "h1", "2026-01-02"),
            ("b", "h1", "2026-01-01"),
            ("a", "h1", "2026-01-01"),
            ("d", "h2", "2026-01-03"),
        ]
    )

    _run(engine, "upgrade")

    with engine.connect() as connection:
        kept = connection.execute(sa.select(_table(table).c.id).order_by(_table(table).c.id)).scalars().all()
    assert kept == ["a", "d"]
