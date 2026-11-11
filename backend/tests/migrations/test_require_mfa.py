"""Tests for the migration that adds the "Require MFA" server setting (revision 77)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/77_require_mfa.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("require_mfa", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_revision_follows_migration_76():
    migration = _migration_module()
    assert (migration.revision, migration.down_revision) == ("a77c4e8f1b26", "f76d4b8e1c35")


def test_the_upgrade_adds_a_non_null_setting_that_is_off():
    migration = _migration_module()
    with (
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "create_check_constraint"),
    ):
        migration.upgrade()

    table, column = add_column.call_args.args
    assert (table, column.name, column.nullable) == ("server_settings", "require_mfa", False)
    assert isinstance(column.type, sa.String)
    assert str(column.server_default.arg) == "off"


def test_the_upgrade_restricts_the_setting_to_its_three_values():
    migration = _migration_module()
    with patch.object(migration.op, "add_column"), patch.object(migration.op, "create_check_constraint") as check:
        migration.upgrade()

    check.assert_called_once_with(
        "require_mfa_check", "server_settings", "require_mfa IN ('off', 'administrators', 'everyone')"
    )


def test_the_downgrade_drops_the_constraint_then_the_column():
    migration = _migration_module()
    with (
        patch.object(migration.op, "drop_constraint") as drop_constraint,
        patch.object(migration.op, "drop_column") as drop_column,
    ):
        migration.downgrade()

    drop_constraint.assert_called_once_with("require_mfa_check", "server_settings", type_="check")
    drop_column.assert_called_once_with("server_settings", "require_mfa")
