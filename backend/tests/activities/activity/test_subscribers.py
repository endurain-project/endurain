"""Tests for the activity notification subscribers (activity.created)."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from infra.events import new_event


def _event(payload):
    return new_event("activity.created", payload, source="test")


class TestOnActivityCreatedNotify:
    """The bus wrapper: creates the notification, swallowing any error."""

    @patch("modules.activities.activity.subscribers.notifications_utils")
    def test_noop_for_non_int_activity_id(self, mock_notif):
        from modules.activities.activity.subscribers import on_activity_created_notify

        on_activity_created_notify(_event({"activity_id": "x", "user_id": 2}))

        mock_notif.create_activity_created_notification.assert_not_called()

    @patch("modules.activities.activity.subscribers.notifications_utils")
    def test_noop_when_user_id_missing(self, mock_notif):
        from modules.activities.activity.subscribers import on_activity_created_notify

        on_activity_created_notify(_event({"activity_id": 1}))

        mock_notif.create_activity_created_notification.assert_not_called()

    @patch("modules.activities.activity.subscribers.websocket_utils")
    @patch("modules.activities.activity.subscribers.websocket_manager")
    @patch("modules.activities.activity.subscribers.platform_async_bridge")
    @patch("modules.activities.activity.subscribers.core_database")
    @patch("modules.activities.activity.subscribers.notifications_utils")
    def test_creates_notification_and_dispatches(self, mock_notif, mock_db, mock_bridge, mock_ws_mgr, mock_ws_utils):
        from modules.activities.activity.subscribers import on_activity_created_notify

        mock_notif.create_activity_created_notification.return_value = (
            MagicMock(id=5),
            "NEW_ACTIVITY_NOTIFICATION",
        )

        on_activity_created_notify(_event({"activity_id": 1, "user_id": 2, "duplicate_start_time": False}))

        # Row created for the owner with the (not-duplicate) flag.
        assert mock_notif.create_activity_created_notification.call_args.args[:3] == (2, 1, False)
        # Websocket push dispatched onto the main loop (best-effort).
        mock_bridge.dispatch.assert_called_once()

    @patch("modules.activities.activity.subscribers.websocket_utils")
    @patch("modules.activities.activity.subscribers.websocket_manager")
    @patch("modules.activities.activity.subscribers.platform_async_bridge")
    @patch("modules.activities.activity.subscribers.core_database")
    @patch("modules.activities.activity.subscribers.notifications_utils")
    def test_passes_duplicate_flag(self, mock_notif, mock_db, mock_bridge, mock_ws_mgr, mock_ws_utils):
        from modules.activities.activity.subscribers import on_activity_created_notify

        mock_notif.create_activity_created_notification.return_value = (
            MagicMock(id=6),
            "NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION",
        )

        on_activity_created_notify(_event({"activity_id": 4, "user_id": 8, "duplicate_start_time": True}))

        assert mock_notif.create_activity_created_notification.call_args.args[:3] == (8, 4, True)

    @patch("infra.subscribers.logger")
    @patch("modules.activities.activity.subscribers.core_database")
    @patch("modules.activities.activity.subscribers.notifications_utils")
    def test_swallows_errors(self, mock_notif, mock_db, mock_logger):
        from modules.activities.activity.subscribers import on_activity_created_notify

        mock_notif.create_activity_created_notification.side_effect = RuntimeError("boom")

        # Must not raise — a notification failure never breaks activity import.
        on_activity_created_notify(_event({"activity_id": 1, "user_id": 2}))

        mock_logger.error.assert_called()

    def test_subscribes_to_created(self):
        from modules.activities.activity.subscribers import (
            on_activity_created_notify,
            register_activity_notification_subscribers,
        )

        events = MagicMock()
        register_activity_notification_subscribers(events)

        events.subscribe.assert_called_once_with("activity.created", on_activity_created_notify)


class TestNotifyActivityCreatedForEvent:
    """The durable core: propagates errors so the job runner can retry."""

    @patch("modules.activities.activity.subscribers.notifications_utils")
    def test_raises_on_missing_ids(self, mock_notif):
        from modules.activities.activity.subscribers import notify_activity_created_for_event

        # A malformed payload (missing user_id) raises so the durable job surfaces
        # it via retry / dead-letter instead of silently completing.
        with pytest.raises(ValidationError):
            notify_activity_created_for_event(_event({"activity_id": 1}))

        mock_notif.create_activity_created_notification.assert_not_called()

    @patch("modules.activities.activity.subscribers.core_database")
    @patch("modules.activities.activity.subscribers.notifications_utils")
    def test_raises_on_error(self, mock_notif, mock_db):
        from modules.activities.activity.subscribers import notify_activity_created_for_event

        mock_notif.create_activity_created_notification.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            notify_activity_created_for_event(_event({"activity_id": 1, "user_id": 2}))

    def test_register_durable_handlers(self):
        from modules.activities.activity.subscribers import (
            ACTIVITY_NOTIFICATION_SUBSCRIBER_ID,
            notify_activity_created_for_event,
            register_activity_notification_durable_handlers,
        )

        registry = MagicMock()
        register_activity_notification_durable_handlers(registry)

        registry.register.assert_called_once_with(
            "activity.created",
            ACTIVITY_NOTIFICATION_SUBSCRIBER_ID,
            notify_activity_created_for_event,
        )
