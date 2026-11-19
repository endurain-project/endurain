"""Tests for the migration that retires the v0.21 data migrations."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_22_0/2_retire_v0_21_data_migrations.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("retire_v0_21_data_migrations", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_upgrade_deletes_the_four_rows_then_drops_the_id_mapping_table():
    migration = _migration_module()
    with patch.object(migration, "op") as op:
        migration.upgrade()

    statements = [str(call.args[0]) for call in op.execute.call_args_list]
    assert statements == [
        "DELETE FROM migrations WHERE id IN (11, 12, 13, 14)",
        "DROP TABLE IF EXISTS uuid_migration_ids",
    ]


def test_the_downgrade_is_refused():
    with pytest.raises(NotImplementedError, match="backup"):
        _migration_module().downgrade()
