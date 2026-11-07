"""Tests for the API key maximum lifetime migration (revision 45)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/45_api_key_max_lifetime.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("api_key_max_lifetime", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_upgrade_adds_the_setting_at_365_days_and_backfills_only_keys_without_an_expiry():
    migration = _migration_module()
    with (
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "create_check_constraint"),
        patch.object(migration.op, "execute") as execute,
        patch.object(migration.op, "alter_column") as alter_column,
    ):
        migration.upgrade()

    table, column = add_column.call_args.args
    assert (table, column.name, str(column.server_default.arg)) == (
        "server_settings",
        "api_key_max_lifetime_days",
        "365",
    )
    statement = str(execute.call_args.args[0])
    assert "expires_at IS NULL" in statement
    assert "interval '365 days'" in statement
    assert alter_column.call_args.kwargs["nullable"] is False
