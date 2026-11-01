"""Tests for the account-security changed notification."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.events import new_event

import core.exceptions as core_exceptions
import modules.auth.account_security.events as account_security_events
import modules.notifications.constants as notifications_constants
import modules.notifications.service as notifications_service
import modules.notifications.subscribers as notification_subscribers


def _event(change="mfa_enabled", idp_id=None):
    payload = {"user_id": 1, "change": change}
    if idp_id is not None:
        payload["idp_id"] = idp_id
    return new_event(account_security_events.ACCOUNT_SECURITY_CHANGED, payload, source="test")


def _create(mock_db, change, idp_id=None, idp=None, created=True):
    with (
        patch("modules.notifications.service.users_integration.get_user", return_value=MagicMock(id=1)),
        patch("modules.notifications.service.idp_integration.get_identity_provider", return_value=idp),
        patch(
            "modules.notifications.service.notifications_crud.create_notification_once",
            return_value=(MagicMock(id=3), created),
        ) as create_once,
    ):
        result = notifications_service.create_account_security_changed_notification(
            1, change, idp_id, "event-1", mock_db
        )
    return result, create_once


class TestCreateAccountSecurityChangedNotification:
    def test_the_type_is_32(self):
        assert notifications_constants.NotificationType.ACCOUNT_SECURITY_CHANGED == 32

    def test_records_the_change(self, mock_db):
        (_, ws_message, created), create_once = _create(mock_db, "password_changed")

        data = create_once.call_args.args[0]
        assert data.user_id == 1
        assert data.type == notifications_constants.NotificationType.ACCOUNT_SECURITY_CHANGED
        assert data.source_event_id == "event-1"
        assert data.options == {"change": "password_changed"}
        assert ws_message == notifications_constants.ACCOUNT_SECURITY_CHANGED_WS_MESSAGE
        assert created is True
        mock_db.commit.assert_called_once()

    def test_an_unlink_records_the_provider(self, mock_db):
        idp = MagicMock()
        idp.name = "Authentik"

        _, create_once = _create(mock_db, "identity_provider_unlinked", 4, idp)

        assert create_once.call_args.args[0].options == {
            "change": "identity_provider_unlinked",
            "idp_id": 4,
            "idp_name": "Authentik",
        }

    def test_an_unlink_of_a_deleted_provider_leaves_the_name_empty(self, mock_db):
        _, create_once = _create(mock_db, "identity_provider_unlinked", 4, None)

        assert create_once.call_args.args[0].options == {
            "change": "identity_provider_unlinked",
            "idp_id": 4,
            "idp_name": None,
        }

    def test_requires_the_user(self, mock_db):
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=None),
            patch("modules.notifications.service.notifications_crud.create_notification_once") as create_once,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            notifications_service.create_account_security_changed_notification(1, "mfa_enabled", None, "e", mock_db)
        create_once.assert_not_called()

    def test_a_redelivered_event_reports_not_created(self, mock_db):
        (_, _, created), _ = _create(mock_db, "mfa_enabled", created=False)

        assert created is False


class TestNotifyAccountSecurityChangedForEvent:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_creates_notification_and_pushes(self, mock_notif, _db, mock_ws):
        mock_notif.create_account_security_changed_notification.return_value = (MagicMock(id=5), "WS", True)
        event = _event("identity_provider_unlinked", 4)

        notification_subscribers.notify_account_security_changed_for_event(event)

        assert mock_notif.create_account_security_changed_notification.call_args.args[:4] == (
            1,
            account_security_events.AccountSecurityChange.IDENTITY_PROVIDER_UNLINKED,
            4,
            event.event_id,
        )
        mock_ws.push_to_user.assert_called_once()

    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_skips_push_for_a_duplicate_event(self, mock_notif, _db, mock_ws):
        mock_notif.create_account_security_changed_notification.return_value = (MagicMock(id=5), "WS", False)

        notification_subscribers.notify_account_security_changed_for_event(_event())

        mock_ws.push_to_user.assert_not_called()

    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_drops_the_event_for_a_missing_user(self, mock_notif, _db, mock_ws):
        mock_notif.create_account_security_changed_notification.side_effect = core_exceptions.NotFoundError("x")

        notification_subscribers.notify_account_security_changed_for_event(_event())

        mock_ws.push_to_user.assert_not_called()

    def test_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)

        assert any(
            c.args[0] == account_security_events.ACCOUNT_SECURITY_CHANGED for c in events.subscribe.call_args_list
        )
        assert any(
            c.args[:2]
            == (
                account_security_events.ACCOUNT_SECURITY_CHANGED,
                notification_subscribers.ACCOUNT_SECURITY_CHANGED_NOTIFICATION_SUBSCRIBER_ID,
            )
            for c in registry.register.call_args_list
        )
