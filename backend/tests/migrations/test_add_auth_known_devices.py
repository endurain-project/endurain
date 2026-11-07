"""Tests for the known-devices migration (revision 36)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/36_add_auth_known_devices.py"


def _migration_module():
    """Load the revision as a Python module."""
    spec = importlib.util.spec_from_file_location("add_auth_known_devices", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_chains_onto_the_previous_head() -> None:
    assert _migration_module().down_revision == "9e4b7a2d6c18"


def test_upgrade_creates_the_table_with_its_unique_key_and_prune_index() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "create_table") as create_table,
        patch.object(migration.op, "create_index") as create_index,
    ):
        migration.upgrade()

    assert create_table.call_args.args[0] == "auth_known_devices"
    columns = {item.name: item for item in create_table.call_args.args[1:] if hasattr(item, "type")}
    assert set(columns) == {"id", "user_id", "device_hash", "created_at", "last_seen_at"}
    assert all(not column.nullable for name, column in columns.items() if name != "id")
    assert columns["created_at"].type.timezone and columns["last_seen_at"].type.timezone
    constraints = [item for item in create_table.call_args.args[1:] if not hasattr(item, "type")]
    foreign_key = next(item for item in constraints if type(item).__name__ == "ForeignKeyConstraint")
    assert foreign_key.ondelete == "CASCADE"
    unique = next(item for item in constraints if type(item).__name__ == "UniqueConstraint")
    assert unique.name == "uq_auth_known_devices_user_id_device_hash"
    assert create_index.call_args.args[1:] == ("auth_known_devices", ["last_seen_at"])


def test_downgrade_drops_the_table() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "drop_index") as drop_index,
        patch.object(migration.op, "drop_table") as drop_table,
    ):
        migration.downgrade()

    drop_index.assert_called_once()
    drop_table.assert_called_once_with("auth_known_devices")
