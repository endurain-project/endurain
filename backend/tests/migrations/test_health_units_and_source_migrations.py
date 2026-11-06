"""Revisions 50 and 51: a default health source, and the unit in the name of the health columns."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_VERSIONS = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0"


def _migration(name: str):
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), _VERSIONS / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_source_migration_requires_a_source_on_all_six_tables_and_restores_nullability():
    migration = _migration("50_health_source_manual_default.py")
    with patch.object(migration.op, "execute") as execute, patch.object(migration.op, "alter_column") as alter:
        migration.upgrade()
    tables = {call.args[0] for call in alter.call_args_list}
    assert tables == {"health_weight", "health_steps", "health_sleep", "health_water", "health_poop", "health_fasting"}
    assert all(
        call.kwargs["nullable"] is False and call.kwargs["server_default"] == "manual" for call in alter.call_args_list
    )
    # Garmin sleep rows keep their provider; every other missing source becomes manual.
    assert "garminconnect_sleep_id IS NOT NULL" in str(execute.call_args_list[0].args[0])
    assert len(execute.call_args_list) == 1 + len(tables)

    with patch.object(migration.op, "alter_column") as alter:
        migration.downgrade()
    assert all(call.kwargs["nullable"] is True for call in alter.call_args_list)


def test_the_units_migration_renames_each_column_and_back():
    migration = _migration("51_health_units_in_column_names.py")
    with patch.object(migration.op, "alter_column") as alter:
        migration.upgrade()
    renamed = {(c.args[0], c.args[1]): c.kwargs["new_column_name"] for c in alter.call_args_list}
    assert renamed[("health_weight", "weight")] == "weight_kg"
    assert renamed[("health_weight", "body_fat")] == "body_fat_percent"
    assert renamed[("health_targets", "sleep")] == "sleep_seconds"
    assert renamed[("health_sleep", "avg_spo2")] == "avg_spo2_percent"

    with patch.object(migration.op, "alter_column") as alter:
        migration.downgrade()
    restored = {(c.args[0], c.kwargs["new_column_name"]): c.args[1] for c in alter.call_args_list}
    assert restored[("health_weight", "weight")] == "weight_kg"
    assert len(alter.call_args_list) == len(renamed)


def test_the_migrations_chain_from_revision_49():
    assert _migration("50_health_source_manual_default.py").down_revision == "a4d8f1c6b273"
    assert (
        _migration("51_health_units_in_column_names.py").down_revision
        == _migration("50_health_source_manual_default.py").revision
    )
