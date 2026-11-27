"""Tests for the migration that retires the v0.20 data migrations."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/10_retire_data_migrations_and_align_schema.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("retire_old_data_migrations", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_upgrade_deletes_the_nine_rows_then_drops_the_cadence_table():
    migration = _migration_module()
    with patch.object(migration, "op") as op:
        migration.upgrade_retire_old_data_migrations()

    statements = [str(call.args[0]) for call in op.execute.call_args_list]
    assert statements == [
        "DELETE FROM migrations WHERE id IN (1, 2, 3, 4, 5, 6, 8, 9, 10)",
        "DROP TABLE cadence_spm_migration_rows",
    ]


def test_the_downgrade_is_refused():
    with pytest.raises(NotImplementedError, match="backup"):
        _migration_module().downgrade_retire_old_data_migrations()
