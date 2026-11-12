"""Tests for the migration that records when an API key was revoked (revision 83)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/83_api_key_revoked_at.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("api_key_revoked_at", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_revision_follows_migration_82():
    assert _migration_module().down_revision == "f82c6d1a9e57"


def test_the_upgrade_adds_a_nullable_aware_column_and_backfills_revoked_keys_with_their_creation_time():
    migration = _migration_module()
    with patch.object(migration.op, "add_column") as add_column, patch.object(migration.op, "execute") as execute:
        migration.upgrade()

    table, column = add_column.call_args.args
    assert table == "users_api_keys"
    assert column.name == "revoked_at"
    assert column.nullable is True
    assert column.type.timezone is True
    statement = str(execute.call_args.args[0])
    assert "SET revoked_at = created_at" in statement
    assert "is_active" in statement


def test_the_downgrade_drops_the_column():
    migration = _migration_module()
    with patch.object(migration.op, "drop_column") as drop_column:
        migration.downgrade()

    drop_column.assert_called_once_with("users_api_keys", "revoked_at")


def test_the_column_type_is_a_timestamp_with_time_zone():
    migration = _migration_module()
    with patch.object(migration.op, "add_column") as add_column, patch.object(migration.op, "execute"):
        migration.upgrade()
    assert isinstance(add_column.call_args.args[1].type, sa.DateTime)
