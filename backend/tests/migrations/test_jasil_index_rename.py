"""Tests for the JASIL event metadata index rename migration."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_20_0/18_rename_jasil_event_metadata_index.py"
)

_CANONICAL_COMMENTS = {
    ("event_log", "event_type"): "Domain-event channel, e.g. order.created",
    ("event_log", "event_source"): "Where the event originated, e.g. api:create_order",
    ("event_log", "event_metadata"): "Correlation context (request_id, plus any host-defined keys)",
    ("event_outbox", "event_type"): "Domain-event channel, e.g. order.created",
    ("event_outbox", "source"): "Where the event originated, e.g. api:create_order",
    ("event_outbox", "event_metadata"): "Correlation context (request_id, plus any host-defined keys)",
    ("processing_jobs", "event_type"): "Domain-event channel, e.g. order.created",
    ("processing_jobs", "subscriber_id"): "Durable subscriber this job runs, e.g. invoice.render",
    ("processing_jobs", "job_metadata"): "Correlation context (request_id, plus any host-defined keys)",
}

_LEGACY_COMMENTS = {
    ("event_log", "event_type"): "Domain-event channel, e.g. activity.created",
    ("event_log", "event_source"): "Where the event originated, e.g. api:store_activity",
    ("event_log", "event_metadata"): "Correlation context (request_id, user_id, activity_id)",
    ("event_outbox", "event_type"): "Domain-event channel, e.g. activity.created",
    ("event_outbox", "source"): "Where the event originated, e.g. api:store_activity",
    ("event_outbox", "event_metadata"): "Correlation context (request_id, user_id, activity_id)",
    ("processing_jobs", "event_type"): "Domain-event channel, e.g. activity.created",
    ("processing_jobs", "subscriber_id"): "Durable subscriber this job runs, e.g. activity_thumbnail.generate",
    ("processing_jobs", "job_metadata"): "Correlation context (request_id, user_id, activity_id)",
}


def _migration_module():
    """Load the index rename revision as a Python module."""
    spec = importlib.util.spec_from_file_location("jasil_index_rename", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _comments_from(alter_column) -> dict[tuple[str, str], str]:
    """Return comments keyed by table and column from mocked alterations."""
    return {(item.args[0], item.args[1]): item.kwargs["comment"] for item in alter_column.call_args_list}


def test_upgrade_renames_the_legacy_index_to_the_jasil_name() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "execute") as execute,
        patch.object(migration.op, "alter_column") as alter_column,
    ):
        migration.upgrade()

    execute.assert_called_once_with("ALTER INDEX idx_event_log_metadata RENAME TO idx_event_log_metadata_gin")
    assert _comments_from(alter_column) == _CANONICAL_COMMENTS


def test_downgrade_restores_the_legacy_index_name() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "execute") as execute,
        patch.object(migration.op, "alter_column") as alter_column,
    ):
        migration.downgrade()

    execute.assert_called_once_with("ALTER INDEX idx_event_log_metadata_gin RENAME TO idx_event_log_metadata")
    assert _comments_from(alter_column) == _LEGACY_COMMENTS
