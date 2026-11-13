"""Tests for the migration that stamps email-change tokens with a security generation (revision 69)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/69_sign_up_token_security_generation.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("sign_up_token_security_generation", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_revision_follows_migration_68():
    migration = _migration_module()
    assert (migration.revision, migration.down_revision) == ("f69b5d8e0c24", "e68a4c7d9b13")


def test_the_upgrade_adds_a_nullable_integer_without_a_backfill():
    migration = _migration_module()
    with patch.object(migration.op, "add_column") as add_column:
        migration.upgrade()

    table, column = add_column.call_args.args
    assert (table, column.name, column.nullable) == ("sign_up_tokens", "security_generation", True)
    assert isinstance(column.type, sa.Integer)


def test_the_downgrade_drops_the_column():
    migration = _migration_module()
    with patch.object(migration.op, "drop_column") as drop_column:
        migration.downgrade()

    drop_column.assert_called_once_with("sign_up_tokens", "security_generation")
