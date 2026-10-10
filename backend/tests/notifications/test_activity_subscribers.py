"""Tests for activity-created notification consumers."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.events import new_event
from pydantic import ValidationError


def _event(payload):
    return new_event("activity.created", payload, source="test")


class TestOnActivityCreatedNotify:
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_noop_for_non_int_activity_id(self, mock_notif):
        from modules.notifications.subscribers import on_activity_created_notify

        on_activity_created_notify(_event({"activity_id": "x", "user_id": 2}))
        mock_notif.create_activity_created_notification.assert_not_called()

    @patch("modules.notifications.subscribers.notifications_integration")
    def test_noop_when_user_id_missing(self, mock_notif):
        from modules.notifications.subscribers import on_activity_created_notify

        on_activity_created_notify(_event({"activity_id": 1}))
        mock_notif.create_activity_created_notification.assert_not_called()

    @patch("modules.notifications.subscribers.websocket_integration")
    @patch("modules.notifications.subscribers.core_async_bridge")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_creates_notification_and_dispatches(self, mock_notif, mock_db, mock_bridge, mock_ws):
        from modules.notifications.subscribers import on_activity_created_notify

        mock_notif.create_activity_created_notification.return_value = (
            MagicMock(id=5),
            "NEW_ACTIVITY_NOTIFICATION",
        )
        on_activity_created_notify(_event({"activity_id": 1, "user_id": 2, "duplicate_start_time": False}))

        assert mock_notif.create_activity_created_notification.call_args.args[:3] == (2, 1, False)
        mock_bridge.dispatch.assert_called_once()

    @patch("modules.notifications.subscribers.websocket_integration")
    @patch("modules.notifications.subscribers.core_async_bridge")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_passes_duplicate_flag(self, mock_notif, mock_db, mock_bridge, mock_ws):
        from modules.notifications.subscribers import on_activity_created_notify

        mock_notif.create_activity_created_notification.return_value = (
            MagicMock(id=6),
            "NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION",
        )
        on_activity_created_notify(_event({"activity_id": 4, "user_id": 8, "duplicate_start_time": True}))
        assert mock_notif.create_activity_created_notification.call_args.args[:3] == (8, 4, True)

    @patch("jasil.subscribers.logger")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_swallows_errors(self, mock_notif, mock_db, mock_logger):
        from modules.notifications.subscribers import on_activity_created_notify

        mock_notif.create_activity_created_notification.side_effect = RuntimeError("boom")
        on_activity_created_notify(_event({"activity_id": 1, "user_id": 2}))
        mock_logger.error.assert_called()


class TestNotifyActivityCreatedForEvent:
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_raises_on_missing_ids(self, mock_notif):
        from modules.notifications.subscribers import notify_activity_created_for_event

        with pytest.raises(ValidationError):
            notify_activity_created_for_event(_event({"activity_id": 1}))
        mock_notif.create_activity_created_notification.assert_not_called()

    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_raises_on_error(self, mock_notif, mock_db):
        from modules.notifications.subscribers import notify_activity_created_for_event

        mock_notif.create_activity_created_notification.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            notify_activity_created_for_event(_event({"activity_id": 1, "user_id": 2}))


class TestRegisterActivityNotificationConsumers:
    def test_subscribes_to_created(self):
        from modules.notifications.subscribers import on_activity_created_notify, register_notification_subscribers

        events = MagicMock()
        register_notification_subscribers(events)
        events.subscribe.assert_any_call("activity.created", on_activity_created_notify)

    def test_registers_durable_handler(self):
        from modules.notifications import subscribers

        registry = MagicMock()
        subscribers.register_notification_durable_handlers(registry)
        registry.register.assert_any_call(
            "activity.created",
            subscribers.ACTIVITY_NOTIFICATION_SUBSCRIBER_ID,
            subscribers.notify_activity_created_for_event,
        )
