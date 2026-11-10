"""Tests for the known-device security-generation migration (revision 73)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/73_known_device_security_generation.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("known_device_security_generation", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_chains_onto_the_previous_head() -> None:
    assert _migration_module().down_revision == "b72f5d0a3c81"


def test_upgrade_backfills_each_device_with_its_users_current_generation() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "execute") as execute,
        patch.object(migration.op, "alter_column"),
    ):
        migration.upgrade()

    added = {call.args[1].name for call in add_column.call_args_list}
    assert added == {"security_generation", "browser", "operating_system", "device_type"}
    statement = execute.call_args.args[0]
    assert "SET security_generation = account_security_generations.generation" in statement
    assert "account_security_generations.user_id = auth_known_devices.user_id" in statement
