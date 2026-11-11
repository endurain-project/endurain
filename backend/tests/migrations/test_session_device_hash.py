"""Tests for the migration that records the known device a session signed in from (revision 81)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/81_session_device_hash.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("session_device_hash", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_revision_follows_migration_80():
    migration = _migration_module()
    assert (migration.revision, migration.down_revision) == ("e81a5c7d0b34", "d80f4b6c2e93")


def test_the_upgrade_adds_a_nullable_hash_column_without_a_backfill():
    migration = _migration_module()
    with patch.object(migration.op, "add_column") as add_column:
        migration.upgrade()

    table, column = add_column.call_args.args
    assert (table, column.name, column.nullable) == ("users_sessions", "device_hash", True)
    assert isinstance(column.type, sa.String)
    assert column.type.length == 64


def test_the_downgrade_drops_the_column():
    migration = _migration_module()
    with patch.object(migration.op, "drop_column") as drop_column:
        migration.downgrade()

    drop_column.assert_called_once_with("users_sessions", "device_hash")
