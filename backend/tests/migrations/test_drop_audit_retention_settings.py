"""Tests for the migration that drops the audit retention settings (revision 82)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/82_drop_audit_retention_settings.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("drop_audit_retention_settings", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_revision_follows_migration_81():
    migration = _migration_module()
    assert migration.down_revision == "e81a5c7d0b34"


def test_the_upgrade_drops_the_constraint_and_both_columns():
    migration = _migration_module()
    with (
        patch.object(migration.op, "drop_constraint") as drop_constraint,
        patch.object(migration.op, "drop_column") as drop_column,
    ):
        migration.upgrade()

    drop_constraint.assert_called_once_with("audit_retention_days_check", "server_settings", type_="check")
    assert [call.args for call in drop_column.call_args_list] == [
        ("server_settings", "audit_legal_hold"),
        ("server_settings", "audit_retention_days"),
    ]


def test_the_downgrade_restores_the_columns_with_their_defaults_and_the_constraint():
    migration = _migration_module()
    with (
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "create_check_constraint") as create_constraint,
    ):
        migration.downgrade()

    columns = {call.args[1].name: call.args[1] for call in add_column.call_args_list}
    assert set(columns) == {"audit_retention_days", "audit_legal_hold"}
    assert isinstance(columns["audit_retention_days"].type, sa.Integer)
    assert str(columns["audit_retention_days"].server_default.arg) == "90"
    assert str(columns["audit_legal_hold"].server_default.arg) == "false"
    assert create_constraint.call_args.args[:2] == ("audit_retention_days_check", "server_settings")
