"""Tests for the gate that refuses the upgrade while a v0.21 data migration is pending."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_VERSIONS = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_22_0"
_ALL_FOUR = (11, 12, 13, 14)


def _migration_module():
    path = _VERSIONS / "1_upgrade_gates.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade(users: int, rows: dict[int, bool]) -> None:
    engine = sa.create_engine("sqlite://")
    try:
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
                _migration_module().upgrade_require_v0_21_data_migrations()
    finally:
        engine.dispose()


def test_a_fresh_install_without_users_passes_with_every_migration_pending():
    _upgrade(0, {migration_id: False for migration_id in (7, *_ALL_FOUR)})


def test_the_upgrade_passes_when_all_four_data_migrations_are_executed():
    _upgrade(1, {**{migration_id: True for migration_id in _ALL_FOUR}, 7: True})


def test_the_upgrade_names_the_absent_and_pending_migrations_in_order():
    rows = {migration_id: True for migration_id in _ALL_FOUR if migration_id != 14}
    rows[12] = False
    with pytest.raises(RuntimeError) as error:
        _upgrade(1, rows)
    message = str(error.value)
    assert message.startswith("Data migrations 12, 14 ")
    assert "v0.21.x" in message


def test_every_data_migration_missing_is_named():
    with pytest.raises(RuntimeError, match=r"Data migrations 11, 12, 13, 14 "):
        _upgrade(2, {})
