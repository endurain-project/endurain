"""Tests for the durable bulk-import-file subscriber."""

from unittest.mock import patch

import pytest

import modules.activities.activity_ingestion.bulk_import_subscribers as bulk_import_subscribers
import modules.activities.activity_ingestion.events as ingestion_events
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry


def _event(payload: dict, retry_count: int = 1) -> Event:
    return Event(
        event_id="evt-1",
        event_type=ingestion_events.ACTIVITY_BULK_IMPORT_FILE,
        source="api:bulk_import",
        timestamp="2026-07-21T00:00:00+00:00",
        payload=payload,
        metadata={},
        retry_count=retry_count,
    )


class TestPublishBulkImportFile:
    def test_publishes_durable_event(self):
        with patch.object(bulk_import_subscribers.platform_publisher, "publish") as publish:
            bulk_import_subscribers.publish_bulk_import_file("/tmp/x.gpx", 3, "2026-07-21", "db")
        publish.assert_called_once()
        args, kwargs = publish.call_args
        assert args[0] == ingestion_events.ACTIVITY_BULK_IMPORT_FILE
        assert args[1] == {"file_path": "/tmp/x.gpx", "user_id": 3, "import_initiated_time": "2026-07-21"}
        assert kwargs["source"] == "api:bulk_import"
        assert kwargs["db"] == "db"


class TestProcessBulkImportFileForEvent:
    def test_processes_file(self):
        event = _event({"file_path": "/tmp/x.gpx", "user_id": 3, "import_initiated_time": "2026-07-21"})
        with (
            patch.object(bulk_import_subscribers.core_database, "SessionLocal") as session_local,
            patch.object(bulk_import_subscribers.orchestrator, "store_bulk_import_file") as store,
        ):
            session_local.return_value.__enter__.return_value = "db"
            bulk_import_subscribers.process_bulk_import_file_for_event(event)
        store.assert_called_once_with(3, "/tmp/x.gpx", "2026-07-21", "db")

    def test_noop_on_missing_file_path(self):
        event = _event({"user_id": 3})
        with patch.object(bulk_import_subscribers.orchestrator, "store_bulk_import_file") as store:
            bulk_import_subscribers.process_bulk_import_file_for_event(event)
        store.assert_not_called()

    def test_noop_on_non_int_user(self):
        event = _event({"file_path": "/tmp/x.gpx", "user_id": None})
        with patch.object(bulk_import_subscribers.orchestrator, "store_bulk_import_file") as store:
            bulk_import_subscribers.process_bulk_import_file_for_event(event)
        store.assert_not_called()

    def test_reraises_without_moving_before_last_attempt(self):
        event = _event({"file_path": "/tmp/x.gpx", "user_id": 3, "import_initiated_time": "2026"}, retry_count=2)
        with (
            patch.object(bulk_import_subscribers.core_config.settings, "JOBS_MAX_ATTEMPTS", 3),
            patch.object(bulk_import_subscribers.core_database, "SessionLocal") as session_local,
            patch.object(
                bulk_import_subscribers.orchestrator, "store_bulk_import_file", side_effect=ValueError("boom")
            ),
            patch.object(bulk_import_subscribers, "_move_to_error_dir") as move,
        ):
            session_local.return_value.__enter__.return_value = "db"
            with pytest.raises(ValueError):
                bulk_import_subscribers.process_bulk_import_file_for_event(event)
        move.assert_not_called()

    def test_reraises_and_moves_on_last_attempt(self):
        event = _event({"file_path": "/tmp/x.gpx", "user_id": 3, "import_initiated_time": "2026"}, retry_count=3)
        with (
            patch.object(bulk_import_subscribers.core_config.settings, "JOBS_MAX_ATTEMPTS", 3),
            patch.object(bulk_import_subscribers.core_database, "SessionLocal") as session_local,
            patch.object(
                bulk_import_subscribers.orchestrator, "store_bulk_import_file", side_effect=ValueError("boom")
            ),
            patch.object(bulk_import_subscribers, "_move_to_error_dir") as move,
        ):
            session_local.return_value.__enter__.return_value = "db"
            with pytest.raises(ValueError):
                bulk_import_subscribers.process_bulk_import_file_for_event(event)
        move.assert_called_once_with("/tmp/x.gpx")


class TestMoveToErrorDir:
    def test_moves_file_to_error_dir(self):
        with (
            patch.object(bulk_import_subscribers.core_config, "FILES_BULK_IMPORT_IMPORT_ERRORS_DIR", "/errs"),
            patch.object(bulk_import_subscribers.os, "makedirs") as makedirs,
            patch.object(bulk_import_subscribers.core_file_uploads, "move_within") as move_within,
            patch.object(bulk_import_subscribers.core_logger, "print_to_log_and_console"),
        ):
            bulk_import_subscribers._move_to_error_dir("/tmp/x.gpx")
        makedirs.assert_called_once_with("/errs", exist_ok=True)
        move_within.assert_called_once_with("/tmp/x.gpx", "/errs", filename="x.gpx")

    def test_swallows_oserror(self):
        with (
            patch.object(bulk_import_subscribers.os, "makedirs", side_effect=OSError("nope")),
            patch.object(bulk_import_subscribers.core_logger, "print_to_log_and_console") as log,
        ):
            bulk_import_subscribers._move_to_error_dir("/tmp/x.gpx")
        assert log.called


class TestRegisterBulkImportDurableHandlers:
    def test_registers_handler(self):
        registry = JobHandlerRegistry()
        bulk_import_subscribers.register_bulk_import_durable_handlers(registry)
        assert registry.subscribers_for(ingestion_events.ACTIVITY_BULK_IMPORT_FILE) == (
            bulk_import_subscribers.BULK_IMPORT_FILE_SUBSCRIBER_ID,
        )
        assert (
            registry.get(bulk_import_subscribers.BULK_IMPORT_FILE_SUBSCRIBER_ID)
            is bulk_import_subscribers.process_bulk_import_file_for_event
        )
