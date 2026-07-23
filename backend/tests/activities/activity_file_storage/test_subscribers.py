"""Tests for the activity source-file cleanup subscriber."""

from unittest.mock import MagicMock, patch

import modules.activities.activity.events as activity_events
from infra.events import new_event


def _deleted_event(payload):
    return new_event(activity_events.ACTIVITY_DELETED, payload, source="test")


class TestCleanupActivityFileForEvent:
    @patch("modules.activities.activity_file_storage.subscribers.platform_runtime")
    def test_noop_for_non_int_activity_id(self, mock_runtime):
        from modules.activities.activity_file_storage.subscribers import cleanup_activity_file_for_event

        cleanup_activity_file_for_event(_deleted_event({"activity_id": "x"}))

        mock_runtime.get_active_platform.assert_not_called()

    @patch("modules.activities.activity_file_storage.service.delete_activity_file")
    @patch("modules.activities.activity_file_storage.subscribers.platform_runtime")
    def test_deletes_via_service(self, mock_runtime, mock_delete):
        from modules.activities.activity_file_storage.subscribers import cleanup_activity_file_for_event

        storage = MagicMock()
        mock_runtime.get_active_platform.return_value.storage = storage

        cleanup_activity_file_for_event(_deleted_event({"activity_id": 42}))

        mock_delete.assert_called_once_with(42, storage)


class TestOnActivityDeletedCleanupFile:
    @patch("modules.activities.activity_file_storage.subscribers.cleanup_activity_file_for_event")
    def test_swallows_errors(self, mock_core):
        from modules.activities.activity_file_storage.subscribers import on_activity_deleted_cleanup_file

        mock_core.side_effect = RuntimeError("boom")

        # A cleanup failure must never propagate out of the bus handler.
        on_activity_deleted_cleanup_file(_deleted_event({"activity_id": 42}))

    @patch("modules.activities.activity_file_storage.subscribers.cleanup_activity_file_for_event")
    def test_delegates_to_core(self, mock_core):
        from modules.activities.activity_file_storage.subscribers import on_activity_deleted_cleanup_file

        event = _deleted_event({"activity_id": 42})
        on_activity_deleted_cleanup_file(event)

        mock_core.assert_called_once_with(event)


class TestRegistration:
    def test_register_bus_subscribes_deleted(self):
        from modules.activities.activity_file_storage.subscribers import register_activity_file_cleanup_subscribers

        events = MagicMock()
        register_activity_file_cleanup_subscribers(events)

        events.subscribe.assert_called_once()
        assert events.subscribe.call_args[0][0] == activity_events.ACTIVITY_DELETED

    def test_register_durable_registers_handler(self):
        from modules.activities.activity_file_storage.subscribers import (
            ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID,
            register_activity_file_cleanup_durable_handlers,
        )

        registry = MagicMock()
        register_activity_file_cleanup_durable_handlers(registry)

        registry.register.assert_called_once()
        args = registry.register.call_args[0]
        assert args[0] == activity_events.ACTIVITY_DELETED
        assert args[1] == ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID
