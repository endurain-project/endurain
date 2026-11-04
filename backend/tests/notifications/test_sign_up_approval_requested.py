"""Tests for the admin sign-up approval request notification."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.events import new_event

import core.exceptions as core_exceptions
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.notifications.constants as notifications_constants
import modules.notifications.service as notifications_service
import modules.notifications.subscribers as notification_subscribers


def _event():
    return new_event(sign_up_events.SIGN_UP_APPROVAL_REQUESTED, {"user_id": 9, "admin_user_id": 2}, source="test")


class TestCreateAdminSignUpApprovalNotification:
    def test_names_the_new_user_and_belongs_to_the_admin(self, mock_db):
        user = MagicMock(id=9)
        user.name = "New"
        user.username = "new"
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=user),
            patch(
                "modules.notifications.service.notifications_crud.create_notification_once",
                return_value=(MagicMock(id=3), True),
            ) as create_once,
        ):
            _, ws_message, created = notifications_service.create_admin_sign_up_approval_notification(
                9, 2, "event-1", mock_db
            )

        data = create_once.call_args.args[0]
        assert data.user_id == 2
        assert data.type == notifications_constants.NotificationType.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST
        assert data.source_event_id == "event-1"
        assert data.options == {"user_id": 9, "user_name": "New", "user_username": "new"}
        assert ws_message == notifications_constants.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_WS_MESSAGE
        assert created is True
        mock_db.commit.assert_called_once()

    def test_requires_the_user(self, mock_db):
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            notifications_service.create_admin_sign_up_approval_notification(9, 2, "event-1", mock_db)


class TestNotifyAdminSignUpApprovalForEvent:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_creates_notification_and_pushes_to_the_admin(self, mock_notif, mock_db, mock_ws):
        mock_notif.create_admin_sign_up_approval_notification.return_value = (
            MagicMock(id=5),
            notifications_constants.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_WS_MESSAGE,
            True,
        )
        event = _event()

        notification_subscribers.notify_admin_sign_up_approval_for_event(event)

        assert mock_notif.create_admin_sign_up_approval_notification.call_args.args[:3] == (9, 2, event.event_id)
        mock_ws.push_to_user.assert_called_once()
        assert mock_ws.push_to_user.call_args.args[0] == 2

    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_skips_push_for_a_duplicate_event(self, mock_notif, mock_db, mock_ws):
        mock_notif.create_admin_sign_up_approval_notification.return_value = (MagicMock(id=5), "X", False)

        notification_subscribers.notify_admin_sign_up_approval_for_event(_event())

        mock_ws.push_to_user.assert_not_called()

    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_drops_the_event_for_a_missing_user(self, mock_notif, mock_db, mock_ws):
        mock_notif.create_admin_sign_up_approval_notification.side_effect = core_exceptions.NotFoundError("gone")

        notification_subscribers.notify_admin_sign_up_approval_for_event(_event())

        mock_ws.push_to_user.assert_not_called()

    def test_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)

        assert any(c.args[0] == sign_up_events.SIGN_UP_APPROVAL_REQUESTED for c in events.subscribe.call_args_list)
        assert any(
            c.args[:2]
            == (
                sign_up_events.SIGN_UP_APPROVAL_REQUESTED,
                notification_subscribers.ADMIN_SIGN_UP_APPROVAL_NOTIFICATION_SUBSCRIBER_ID,
            )
            for c in registry.register.call_args_list
        )
