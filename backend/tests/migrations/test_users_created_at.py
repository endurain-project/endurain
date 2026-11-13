"""Tests for the migration that adds ``created_at`` to ``users`` (revision 59)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/59_users_created_at.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("users_created_at", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_upgrade_adds_a_non_null_timezone_aware_column_that_defaults_to_now():
    migration = _migration_module()
    with patch.object(migration.op, "add_column") as add_column:
        migration.upgrade()

    table, column = add_column.call_args.args
    assert (table, column.name, column.nullable) == ("users", "created_at", False)
    assert isinstance(column.type, sa.DateTime)
    assert column.type.timezone is True
    assert isinstance(column.server_default.arg, sa.sql.functions.now)


def test_the_downgrade_drops_the_column():
    migration = _migration_module()
    with patch.object(migration.op, "drop_column") as drop_column:
        migration.downgrade()

    drop_column.assert_called_once_with("users", "created_at")
