"""Tests for the migration that refuses the upgrade while a v0.20 data migration is pending (revision 0)."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_VERSIONS = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0"
_ALL_NINE = (1, 2, 3, 4, 5, 6, 8, 9, 10)


def _module(filename: str):
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migration_module():
    return _module("0_require_v0_20_data_migrations.py")


def _upgrade(users: int, rows: dict[int, bool]) -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE migrations (id INTEGER PRIMARY KEY, executed BOOLEAN NOT NULL)"))
        for user_id in range(1, users + 1):
            conn.execute(sa.text("INSERT INTO users (id) VALUES (:id)"), {"id": user_id})
        for migration_id, executed in rows.items():
            conn.execute(
                sa.text("INSERT INTO migrations (id, executed) VALUES (:id, :executed)"),
                {"id": migration_id, "executed": executed},
            )
        with Operations.context(MigrationContext.configure(conn)):
            _migration_module().upgrade()


def test_the_revision_follows_the_v0_20_head_and_revision_1_follows_it():
    migration = _migration_module()
    assert (migration.revision, migration.down_revision) == ("c5cfe02a11c2", "d54bdd779392")
    assert _module("1_gear_nickname_unique_per_user.py").down_revision == migration.revision


def test_a_fresh_install_without_users_passes_with_every_migration_pending():
    _upgrade(0, {migration_id: False for migration_id in (*_ALL_NINE, 11, 12)})


def test_the_upgrade_passes_when_all_nine_data_migrations_are_executed():
    _upgrade(1, {**{migration_id: True for migration_id in _ALL_NINE}, 7: True, 11: False})


def test_the_upgrade_names_the_absent_and_pending_migrations_in_order():
    rows = {migration_id: True for migration_id in _ALL_NINE if migration_id != 9}
    rows[3] = False
    with pytest.raises(RuntimeError) as error:
        _upgrade(1, rows)
    message = str(error.value)
    assert message.startswith("Data migrations 3, 9 ")
    assert "v0.20.x" in message


def test_every_data_migration_missing_is_named():
    with pytest.raises(RuntimeError, match=r"Data migrations 1, 2, 3, 4, 5, 6, 8, 9, 10 "):
        _upgrade(2, {})
