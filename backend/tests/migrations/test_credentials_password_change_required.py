"""Tests for the migration that adds ``password_change_required`` to the local credentials (revision 55)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/55_credentials_password_change_required.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("credentials_password_change_required", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_upgrade_adds_a_non_null_flag_that_is_false_for_existing_credentials():
    migration = _migration_module()
    with patch.object(migration.op, "add_column") as add_column:
        migration.upgrade()

    table, column = add_column.call_args.args
    assert (table, column.name, column.nullable) == ("users_local_credentials", "password_change_required", False)
    assert str(column.server_default.arg) == "false"


def test_the_downgrade_drops_the_flag():
    migration = _migration_module()
    with patch.object(migration.op, "drop_column") as drop_column:
        migration.downgrade()

    drop_column.assert_called_once_with("users_local_credentials", "password_change_required")
