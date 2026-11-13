"""Tests for the new-device sign-in notification."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from jasil.events import new_event

import core.exceptions as core_exceptions
import modules.auth.known_devices.events as known_devices_events
import modules.notifications.constants as notifications_constants
import modules.notifications.service as notifications_service
import modules.notifications.subscriber_registry as notification_subscriber_registry
import modules.notifications.subscribers as notification_subscribers

_ID_1 = uuid.uuid4()


def _event():
    payload = {
        "user_id": str(_ID_1),
        "browser": "Firefox",
        "operating_system": "Linux",
        "device_type": "PC",
        "ip_address": "203.0.113.7",
        "method": "password",
        "signed_in_at": datetime(2026, 11, 1, 12, 5, tzinfo=UTC).isoformat(),
    }
    return new_event(known_devices_events.NEW_DEVICE_SIGN_IN, payload, source="test")


def _create(mock_db, created=True):
    with (
        patch("modules.notifications.service.users_integration.get_user", return_value=MagicMock(id=_ID_1)),
        patch(
            "modules.notifications.service.notifications_crud.create_notification_once",
            return_value=(MagicMock(id=uuid.UUID(int=3)), created),
        ) as create_once,
    ):
        result = notifications_service.create_new_device_sign_in_notification(
            _ID_1, "Firefox", "Linux", "203.0.113.7", "event-1", mock_db
        )
    return result, create_once


class TestCreateNewDeviceSignInNotification:
    def test_the_type_is_33(self):
        assert notifications_constants.NotificationType.NEW_DEVICE_SIGN_IN.stored == 33

    def test_records_the_browser_the_system_and_the_address(self, mock_db):
        (_, ws_message, created), create_once = _create(mock_db)

        data = create_once.call_args.args[0]
        assert data.user_id == _ID_1
        assert data.type == notifications_constants.NotificationType.NEW_DEVICE_SIGN_IN
        assert data.source_event_id == "event-1"
        assert data.options == {"browser": "Firefox", "operating_system": "Linux", "ip_address": "203.0.113.7"}
        assert ws_message == notifications_constants.NEW_DEVICE_SIGN_IN_WS_MESSAGE == "NEW_DEVICE_SIGN_IN_NOTIFICATION"
        assert created is True
        mock_db.commit.assert_called_once()

    def test_requires_the_user(self, mock_db):
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=None),
            patch("modules.notifications.service.notifications_crud.create_notification_once") as create_once,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            notifications_service.create_new_device_sign_in_notification(_ID_1, "Firefox", "Linux", "ip", "e", mock_db)
        create_once.assert_not_called()

    def test_a_redelivered_event_reports_not_created(self, mock_db):
        (_, _, created), _ = _create(mock_db, created=False)

        assert created is False


class TestNotifyNewDeviceSignInForEvent:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_creates_notification_and_pushes(self, mock_notif, _db, mock_ws):
        mock_notif.create_new_device_sign_in_notification.return_value = (MagicMock(id=uuid.UUID(int=5)), "WS", True)
        event = _event()

        notification_subscribers.notify_new_device_sign_in_for_event(event)

        assert mock_notif.create_new_device_sign_in_notification.call_args.args[:5] == (
            _ID_1,
            "Firefox",
            "Linux",
            "203.0.113.7",
            event.event_id,
        )
        mock_ws.push_to_user.assert_called_once()

    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_skips_push_for_a_duplicate_event(self, mock_notif, _db, mock_ws):
        mock_notif.create_new_device_sign_in_notification.return_value = (MagicMock(id=uuid.UUID(int=5)), "WS", False)

        notification_subscribers.notify_new_device_sign_in_for_event(_event())

        mock_ws.push_to_user.assert_not_called()

    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_drops_the_event_for_a_missing_user(self, mock_notif, _db, mock_ws):
        mock_notif.create_new_device_sign_in_notification.side_effect = core_exceptions.NotFoundError("gone")

        notification_subscribers.notify_new_device_sign_in_for_event(_event())

        mock_ws.push_to_user.assert_not_called()


class TestRegistration:
    def test_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)

        events.subscribe.assert_any_call(
            known_devices_events.NEW_DEVICE_SIGN_IN, notification_subscribers.on_new_device_sign_in_notify
        )
        registry.register.assert_any_call(
            known_devices_events.NEW_DEVICE_SIGN_IN,
            "auth.notify_new_device_sign_in",
            notification_subscribers.notify_new_device_sign_in_for_event,
        )

    def test_its_net_is_exempt_with_a_reason(self):
        net = next(
            net
            for net in notification_subscriber_registry.DURABLE_SUBSCRIBER_NETS
            if net.subscriber_id == "auth.notify_new_device_sign_in"
        )

        assert net.exempt_reason
