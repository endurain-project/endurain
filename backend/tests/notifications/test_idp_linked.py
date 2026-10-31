"""Tests for the identity-provider linked notification."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.events import new_event

import core.exceptions as core_exceptions
import modules.auth.identity_providers.events as idp_events
import modules.notifications.constants as notifications_constants
import modules.notifications.service as notifications_service
import modules.notifications.subscribers as notification_subscribers


def _event():
    return new_event(idp_events.IDP_LINKED, {"user_id": 1, "idp_id": 4}, source="test")


class TestCreateIdpLinkedNotification:
    def test_records_the_provider_name(self, mock_db):
        idp = MagicMock()
        idp.name = "Authentik"
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=MagicMock(id=1)),
            patch("modules.notifications.service.idp_integration.get_identity_provider", return_value=idp),
            patch(
                "modules.notifications.service.notifications_crud.create_notification_once",
                return_value=(MagicMock(id=3), True),
            ) as create_once,
        ):
            _, ws_message, created = notifications_service.create_idp_linked_notification(1, 4, "event-1", mock_db)

        data = create_once.call_args.args[0]
        assert data.user_id == 1
        assert data.type == notifications_constants.NotificationType.IDP_LINKED
        assert data.source_event_id == "event-1"
        assert data.options == {"idp_id": 4, "idp_name": "Authentik"}
        assert ws_message == notifications_constants.IDP_LINKED_WS_MESSAGE
        assert created is True
        mock_db.commit.assert_called_once()

    def test_a_deleted_provider_leaves_the_name_empty(self, mock_db):
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=MagicMock(id=1)),
            patch("modules.notifications.service.idp_integration.get_identity_provider", return_value=None),
            patch(
                "modules.notifications.service.notifications_crud.create_notification_once",
                return_value=(MagicMock(id=3), True),
            ) as create_once,
        ):
            notifications_service.create_idp_linked_notification(1, 4, "event-1", mock_db)

        assert create_once.call_args.args[0].options == {"idp_id": 4, "idp_name": None}

    def test_requires_the_user(self, mock_db):
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=None),
            patch("modules.notifications.service.notifications_crud.create_notification_once") as create_once,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            notifications_service.create_idp_linked_notification(1, 4, "event-1", mock_db)
        create_once.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_a_redelivered_event_reports_not_created(self, mock_db):
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=MagicMock(id=1)),
            patch("modules.notifications.service.idp_integration.get_identity_provider", return_value=None),
            patch(
                "modules.notifications.service.notifications_crud.create_notification_once",
                return_value=(MagicMock(id=3), False),
            ),
        ):
            _, _, created = notifications_service.create_idp_linked_notification(1, 4, "event-1", mock_db)

        assert created is False


class TestNotifyIdpLinkedForEvent:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_creates_notification_and_pushes(self, mock_notif, mock_db, mock_ws):
        mock_notif.create_idp_linked_notification.return_value = (MagicMock(id=5), "IDP_LINKED_NOTIFICATION", True)
        event = _event()

        notification_subscribers.notify_idp_linked_for_event(event)

        assert mock_notif.create_idp_linked_notification.call_args.args[:3] == (1, 4, event.event_id)
        mock_ws.push_to_user.assert_called_once()

    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_skips_push_for_a_duplicate_event(self, mock_notif, mock_db, mock_ws):
        mock_notif.create_idp_linked_notification.return_value = (MagicMock(id=5), "IDP_LINKED_NOTIFICATION", False)

        notification_subscribers.notify_idp_linked_for_event(_event())

        mock_ws.push_to_user.assert_not_called()

    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_drops_the_event_for_a_missing_user(self, mock_notif, mock_db, mock_ws):
        mock_notif.create_idp_linked_notification.side_effect = core_exceptions.NotFoundError("User not found")

        notification_subscribers.notify_idp_linked_for_event(_event())

        mock_ws.push_to_user.assert_not_called()

    def test_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)

        assert any(c.args[0] == idp_events.IDP_LINKED for c in events.subscribe.call_args_list)
        assert any(
            c.args[:2] == (idp_events.IDP_LINKED, notification_subscribers.IDP_LINKED_NOTIFICATION_SUBSCRIBER_ID)
            for c in registry.register.call_args_list
        )
