"""Tests for the migration that adds the SSO sign-up switch (revision 68)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/68_signup_sso_enabled.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("signup_sso_enabled", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_revision_follows_migration_67():
    migration = _migration_module()
    assert (migration.revision, migration.down_revision) == ("e68a4c7d9b13", "3f7a9c1e5b82")


def test_the_upgrade_adds_a_non_null_switch_that_is_off_for_existing_installs():
    migration = _migration_module()
    with patch.object(migration.op, "add_column") as add_column:
        migration.upgrade()

    table, column = add_column.call_args.args
    assert (table, column.name, column.nullable) == ("server_settings", "signup_sso_enabled", False)
    assert isinstance(column.type, sa.Boolean)
    assert str(column.server_default.arg) == "false"


def test_the_downgrade_drops_the_column():
    migration = _migration_module()
    with patch.object(migration.op, "drop_column") as drop_column:
        migration.downgrade()

    drop_column.assert_called_once_with("server_settings", "signup_sso_enabled")
