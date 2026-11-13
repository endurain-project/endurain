"""Tests for the migration that adds ``updated_at`` and the tombstone tables for incremental sync (revision 78)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

import core.database as core_database
import model_registry

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/78_sync_timestamps.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("sync_timestamps", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metadata() -> sa.MetaData:
    model_registry.import_all_models()
    return core_database.Base.metadata


def _upgrade_calls():
    migration = _migration_module()
    with (
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "create_index") as create_index,
        patch.object(migration.op, "create_table") as create_table,
        patch.object(migration.op, "execute") as execute,
    ):
        migration.upgrade()
    return add_column, create_index, create_table, execute


def test_every_table_that_stamps_updated_at_in_the_models_gets_the_column_and_its_index():
    add_column, create_index, _, _ = _upgrade_calls()
    metadata = _metadata()

    added = {call.args[0]: call.args[1] for call in add_column.call_args_list}
    # Every model on core.sync.UpdatedAtMixin carries the mixin's column comment.
    stamped = {
        name
        for name, table in metadata.tables.items()
        if "updated_at" in table.c and table.c.updated_at.comment == "When the record last changed"
    }
    assert stamped == set(added)
    for table, column in added.items():
        model_column = metadata.tables[table].c.updated_at
        assert (column.name, column.nullable) == ("updated_at", False)
        assert column.type.timezone is model_column.type.timezone is True
        assert isinstance(column.server_default.arg, sa.sql.functions.now)

    indexes = {call.args[0]: (call.args[1], call.args[2]) for call in create_index.call_args_list}
    for table in added:
        model_indexes = {
            index.name: [column.name for column in index.columns] for index in metadata.tables[table].indexes
        }
        name = next(name for name, columns in model_indexes.items() if columns == ["user_id", "updated_at", "id"])
        assert indexes[name] == (table, ["user_id", "updated_at", "id"])


def test_the_tombstone_tables_match_the_models():
    _, create_index, create_table, _ = _upgrade_calls()
    metadata = _metadata()

    created = {
        call.args[0]: [arg for arg in call.args[1:] if isinstance(arg, sa.Column)]
        for call in create_table.call_args_list
    }
    assert set(created) == {
        "activity_deletions",
        "health_record_deletions",
        "gear_deletions",
        "gear_component_deletions",
    }
    indexes = {call.args[0]: (call.args[1], call.args[2]) for call in create_index.call_args_list}
    for table, columns in created.items():
        model = metadata.tables[table]
        assert {column.name for column in columns} == set(model.c.keys())
        for column in columns:
            assert column.nullable == model.c[column.name].nullable
        (index,) = model.indexes
        assert indexes[index.name] == (table, ["user_id", "deleted_at", "id"])


def test_existing_activities_are_stamped_with_when_they_were_recorded():
    _, _, _, execute = _upgrade_calls()

    (statement,) = [call.args[0] for call in execute.call_args_list]
    assert str(statement) == "UPDATE activities SET updated_at = created_at WHERE created_at IS NOT NULL"


def test_the_downgrade_drops_what_the_upgrade_added():
    migration = _migration_module()
    with (
        patch.object(migration.op, "drop_column") as drop_column,
        patch.object(migration.op, "drop_index"),
        patch.object(migration.op, "drop_table") as drop_table,
    ):
        migration.downgrade()

    assert {call.args[0] for call in drop_column.call_args_list} == {table for table, _ in migration._SYNCED}
    assert {call.args[0] for call in drop_table.call_args_list} == {table for table, _, _ in migration._TOMBSTONES}
