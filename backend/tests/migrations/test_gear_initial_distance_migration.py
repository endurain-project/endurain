"""Revision 52: a gear's initial distance in meters."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/52_gear_initial_distance_meters.py"


def _migration():
    spec = importlib.util.spec_from_file_location("gear_initial_distance_meters", _PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_upgrade_widens_converts_to_meters_and_renames():
    migration = _migration()
    with patch.object(migration.op, "alter_column") as alter, patch.object(migration.op, "execute") as execute:
        migration.upgrade()

    assert alter.call_args_list[0].kwargs["type_"].precision == 14
    assert "initial_kms * 1000" in str(execute.call_args.args[0])
    assert alter.call_args_list[1].kwargs["new_column_name"] == "initial_distance"


def test_the_downgrade_renames_back_converts_to_kilometers_and_narrows():
    migration = _migration()
    with patch.object(migration.op, "alter_column") as alter, patch.object(migration.op, "execute") as execute:
        migration.downgrade()

    assert alter.call_args_list[0].kwargs["new_column_name"] == "initial_kms"
    assert "initial_kms / 1000" in str(execute.call_args.args[0])
    assert alter.call_args_list[1].kwargs["type_"].precision == 11


def test_it_follows_revision_51():
    assert _migration().down_revision == "b8c1f4a7d936"
