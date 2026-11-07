"""Tests for the NIST password policy migration (revision 35)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/35_nist_password_policy.py"


def _migration_module():
    """Load the revision as a Python module."""
    spec = importlib.util.spec_from_file_location("nist_password_policy", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_chains_onto_the_previous_head() -> None:
    migration = _migration_module()

    assert migration.down_revision == "2c8f5a1d7e46"


def test_upgrade_drops_password_type_and_moves_old_default_lengths_to_15() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "drop_column") as drop_column,
        patch.object(migration.op, "alter_column") as alter_column,
        patch.object(migration.op, "execute") as execute,
    ):
        migration.upgrade()

    drop_column.assert_called_once_with("server_settings", "password_type")
    assert {(c.args[1], str(c.kwargs["server_default"])) for c in alter_column.call_args_list} == {
        ("password_length_regular_users", "15"),
        ("password_length_admin_users", "15"),
    }
    statements = [c.args[0] for c in execute.call_args_list]
    assert statements == [
        "UPDATE server_settings SET password_length_regular_users = 15 WHERE password_length_regular_users = 8",
        "UPDATE server_settings SET password_length_admin_users = 15 WHERE password_length_admin_users = 12",
    ]


def test_downgrade_restores_password_type_as_strict_and_leaves_lengths() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "alter_column") as alter_column,
        patch.object(migration.op, "execute") as execute,
    ):
        migration.downgrade()

    column = add_column.call_args.args[1]
    assert column.name == "password_type"
    assert column.nullable is False
    assert str(column.server_default.arg) == "strict"
    execute.assert_not_called()
    assert {c.args[1] for c in alter_column.call_args_list} == {
        "password_type",
        "password_length_regular_users",
        "password_length_admin_users",
    }
