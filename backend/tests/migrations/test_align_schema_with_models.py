"""Tests for the migration that aligns the schema with the models (revision 86)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/86_align_schema_with_models.py"

_COMMENTS = {
    ("activity_ingestion_jobs", "id"): (
        "Upload job identifier (UUIDv4 string)",
        "Ingestion job identifier (UUIDv4 string)",
    ),
    ("activity_ingestion_jobs", "user_id"): ("User that owns the upload", "User that owns the ingestion request"),
    ("activity_ingestion_jobs", "created_at"): ("When the upload was accepted", "When the request was accepted"),
    ("health_record_deletions", "record_type"): (
        "Sync type of the record",
        "Sync type of the deleted record, e.g. health_weight",
    ),
}


def _migration_module():
    spec = importlib.util.spec_from_file_location("align_schema_with_models", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _comment_calls(op):
    return {
        (call.args[0], call.args[1]): call.kwargs
        for call in op.alter_column.call_args_list
        if call.args[0] != "activity_sets"
    }


def test_the_revision_follows_revision_85():
    migration = _migration_module()
    assert migration.down_revision == "b41c0afdc9d9"


def test_the_upgrade_makes_start_time_timezone_aware_and_updates_four_comments():
    migration = _migration_module()
    with patch.object(migration, "op") as op:
        migration.upgrade()

    assert op.alter_column.call_count == 5
    start_time = next(call for call in op.alter_column.call_args_list if call.args[0] == "activity_sets")
    assert start_time.args == ("activity_sets", "start_time")
    assert start_time.kwargs["type_"].timezone is True
    assert isinstance(start_time.kwargs["existing_type"], sa.DateTime)
    assert start_time.kwargs["existing_type"].timezone is False
    assert start_time.kwargs["existing_comment"] == "Workout set start date"
    assert "postgresql_using" not in start_time.kwargs
    for key, (old, new) in _COMMENTS.items():
        kwargs = _comment_calls(op)[key]
        assert (kwargs["existing_comment"], kwargs["comment"]) == (old, new)


def test_the_downgrade_restores_the_naive_column_and_the_old_comments():
    migration = _migration_module()
    with patch.object(migration, "op") as op:
        migration.downgrade()

    assert op.alter_column.call_count == 5
    start_time = next(call for call in op.alter_column.call_args_list if call.args[0] == "activity_sets")
    assert start_time.kwargs["type_"].timezone is False
    assert start_time.kwargs["existing_type"].timezone is True
    for key, (old, new) in _COMMENTS.items():
        kwargs = _comment_calls(op)[key]
        assert (kwargs["existing_comment"], kwargs["comment"]) == (new, old)
