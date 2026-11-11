"""Tests for the notifications of a backup code use, a refresh-token reuse and an administrator promotion."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.events import new_event
from pydantic import ValidationError

import core.exceptions as core_exceptions
import modules.auth.account_security.events as account_security_events
import modules.auth.authentication.events as authentication_events
import modules.auth.mfa_backup_codes.events as backup_codes_events
import modules.notifications.constants as notifications_constants
import modules.notifications.schema as notifications_schema
import modules.notifications.service as notifications_service
import modules.notifications.subscribers as notification_subscribers
import modules.users.users.events as users_events

_SERVICE = "modules.notifications.service"
_SUBSCRIBERS = "modules.notifications.subscribers"
_Change = account_security_events.AccountSecurityChange


def _create(mock_db, **kwargs):
    with (
        patch(f"{_SERVICE}.users_integration.get_user", return_value=MagicMock(id=1)),
        patch(
            f"{_SERVICE}.notifications_crud.create_notification_once", return_value=(MagicMock(id=3), True)
        ) as create_once,
    ):
        notifications_service.create_account_security_changed_notification(
            1, kwargs.pop("change"), None, "event-1", mock_db, **kwargs
        )
    return create_once.call_args.args[0]


class TestAccountSecurityChangedOptions:
    def test_a_backup_code_use_records_how_many_codes_are_left(self, mock_db):
        data = _create(mock_db, change="backup_code_used", backup_codes_remaining=3)

        assert data.options == {"change": "backup_code_used", "backup_codes_remaining": 3}

    def test_a_role_change_records_the_new_access_type(self, mock_db):
        data = _create(mock_db, change="role_changed_by_admin", access_type="admin")

        assert data.options == {"change": "role_changed_by_admin", "access_type": "admin"}

    def test_a_change_without_extras_records_only_the_change(self, mock_db):
        data = _create(mock_db, change="refresh_token_reuse_detected")

        assert data.options == {"change": "refresh_token_reuse_detected"}

    def test_the_stored_options_validate_as_a_notification(self):
        notification = notifications_schema.NOTIFICATION_READ_ADAPTER.validate_python(
            {
                "id": 1,
                "user_id": 2,
                "type": "account_security_changed",
                "read": False,
                "created_at": "2026-01-01T00:00:00Z",
                "options": {"change": "backup_code_used", "backup_codes_remaining": 0},
            }
        )

        assert notification.options.backup_codes_remaining == 0


class TestAdminUserPromotedType:
    def test_the_type_is_102(self):
        assert notifications_constants.NotificationType.ADMIN_USER_PROMOTED.stored == 102

    def test_the_notification_names_the_promoted_user(self):
        notification = notifications_schema.NOTIFICATION_READ_ADAPTER.validate_python(
            {
                "id": 1,
                "user_id": 2,
                "type": "admin_user_promoted",
                "read": False,
                "created_at": "2026-01-01T00:00:00Z",
                "options": {"user_id": 3, "user_name": "Ada", "user_username": "ada"},
            }
        )

        assert notification.options.user_username == "ada"

    def test_it_needs_the_named_user(self):
        with pytest.raises(ValidationError):
            notifications_schema.NOTIFICATION_READ_ADAPTER.validate_python(
                {
                    "id": 1,
                    "user_id": 2,
                    "type": "admin_user_promoted",
                    "read": False,
                    "created_at": "2026-01-01T00:00:00Z",
                    "options": {},
                }
            )

    def test_the_service_records_it_for_the_admin_naming_the_promoted_user(self, mock_db):
        user = MagicMock(id=3, username="ada")
        user.name = "Ada"
        with (
            patch(f"{_SERVICE}.users_integration.get_user", return_value=user),
            patch(
                f"{_SERVICE}.notifications_crud.create_notification_once", return_value=(MagicMock(id=3), True)
            ) as create_once,
        ):
            _, ws_message, created = notifications_service.create_admin_user_promoted_notification(
                3, 8, "event-1", mock_db
            )

        data = create_once.call_args.args[0]
        assert data.user_id == 8
        assert data.type == notifications_constants.NotificationType.ADMIN_USER_PROMOTED
        assert data.options == {"user_id": 3, "user_name": "Ada", "user_username": "ada"}
        assert ws_message == notifications_constants.ADMIN_USER_PROMOTED_WS_MESSAGE
        assert created is True


class TestBackupCodeUsedSubscriber:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch(f"{_SUBSCRIBERS}.core_database")
    @patch(f"{_SUBSCRIBERS}.notifications_service")
    def test_notifies_the_owner_with_the_codes_left(self, mock_notif, _db, mock_ws):
        mock_notif.create_account_security_changed_notification.return_value = (MagicMock(id=5), "WS", True)
        event = new_event(
            backup_codes_events.BACKUP_CODE_USED, {"user_id": 4, "backup_codes_remaining": 2}, source="test"
        )

        notification_subscribers.notify_backup_code_used_for_event(event)

        call = mock_notif.create_account_security_changed_notification.call_args
        assert call.args[:4] == (4, _Change.BACKUP_CODE_USED.value, None, event.event_id)
        assert call.kwargs == {"backup_codes_remaining": 2}
        mock_ws.push_to_user.assert_called_once()
        assert mock_ws.push_to_user.call_args.args[0] == 4

    def test_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)

        assert any(c.args[0] == backup_codes_events.BACKUP_CODE_USED for c in events.subscribe.call_args_list)
        assert any(
            c.args[:2] == (backup_codes_events.BACKUP_CODE_USED, "auth.notify_backup_code_used")
            for c in registry.register.call_args_list
        )


class TestRefreshTokenReuseSubscriber:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch(f"{_SUBSCRIBERS}.core_database")
    @patch(f"{_SUBSCRIBERS}.notifications_service")
    def test_notifies_the_owner(self, mock_notif, _db, mock_ws):
        mock_notif.create_account_security_changed_notification.return_value = (MagicMock(id=5), "WS", True)
        event = new_event(authentication_events.REFRESH_REUSE_DETECTED, {"user_id": 4}, source="test")

        notification_subscribers.notify_refresh_reuse_for_event(event)

        assert mock_notif.create_account_security_changed_notification.call_args.args[:4] == (
            4,
            _Change.REFRESH_TOKEN_REUSE_DETECTED.value,
            None,
            event.event_id,
        )
        assert mock_ws.push_to_user.call_args.args[0] == 4

    def test_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)

        assert any(c.args[0] == authentication_events.REFRESH_REUSE_DETECTED for c in events.subscribe.call_args_list)
        assert any(
            c.args[:2] == (authentication_events.REFRESH_REUSE_DETECTED, "auth.notify_refresh_reuse")
            for c in registry.register.call_args_list
        )


class TestAdminPromotedSubscriber:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch(f"{_SUBSCRIBERS}.core_database")
    @patch(f"{_SUBSCRIBERS}.notifications_service")
    def test_notifies_only_the_admin_the_event_names(self, mock_notif, _db, mock_ws):
        mock_notif.create_admin_user_promoted_notification.return_value = (MagicMock(id=5), "WS", True)
        event = new_event(users_events.USERS_ADMIN_PROMOTED, {"user_id": 3, "admin_user_id": 8}, source="test")

        notification_subscribers.notify_admin_user_promoted_for_event(event)

        assert mock_notif.create_admin_user_promoted_notification.call_args.args[:3] == (3, 8, event.event_id)
        mock_ws.push_to_user.assert_called_once()
        assert mock_ws.push_to_user.call_args.args[0] == 8

    @patch("modules.notifications.integration_service.websocket_integration")
    @patch(f"{_SUBSCRIBERS}.core_database")
    @patch(f"{_SUBSCRIBERS}.notifications_service")
    def test_drops_the_event_when_the_promoted_user_is_gone(self, mock_notif, _db, mock_ws):
        mock_notif.create_admin_user_promoted_notification.side_effect = core_exceptions.NotFoundError("x")
        event = new_event(users_events.USERS_ADMIN_PROMOTED, {"user_id": 3, "admin_user_id": 8}, source="test")

        notification_subscribers.notify_admin_user_promoted_for_event(event)

        mock_ws.push_to_user.assert_not_called()

    def test_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)

        assert any(c.args[0] == users_events.USERS_ADMIN_PROMOTED for c in events.subscribe.call_args_list)
        assert any(
            c.args[:2] == (users_events.USERS_ADMIN_PROMOTED, "users.notify_admin_user_promoted")
            for c in registry.register.call_args_list
        )
