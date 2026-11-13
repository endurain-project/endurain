"""Tests for the account-security changed notification."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from jasil.events import new_event

import core.exceptions as core_exceptions
import modules.auth.account_security.events as account_security_events
import modules.auth.authentication.events as authentication_events
import modules.auth.password_reset_tokens.events as password_reset_events
import modules.notifications.constants as notifications_constants
import modules.notifications.service as notifications_service
import modules.notifications.subscribers as notification_subscribers

_ID_1 = uuid.uuid4()

IDP_ID = uuid.UUID(int=4)


def _event(change="mfa_enabled", idp_id=None):
    payload = {"user_id": str(_ID_1), "change": change}
    if idp_id is not None:
        payload["idp_id"] = str(idp_id)
    return new_event(account_security_events.ACCOUNT_SECURITY_CHANGED, payload, source="test")


def _create(mock_db, change, idp_id=None, idp=None, created=True):
    with (
        patch("modules.notifications.service.users_integration.get_user", return_value=MagicMock(id=_ID_1)),
        patch("modules.notifications.service.idp_integration.get_identity_provider", return_value=idp),
        patch(
            "modules.notifications.service.notifications_crud.create_notification_once",
            return_value=(MagicMock(id=uuid.UUID(int=3)), created),
        ) as create_once,
    ):
        result = notifications_service.create_account_security_changed_notification(
            _ID_1, change, idp_id, "event-1", mock_db
        )
    return result, create_once


class TestCreateAccountSecurityChangedNotification:
    def test_the_type_is_32(self):
        assert notifications_constants.NotificationType.ACCOUNT_SECURITY_CHANGED.stored == 32

    def test_records_the_change(self, mock_db):
        (_, ws_message, created), create_once = _create(mock_db, "password_changed")

        data = create_once.call_args.args[0]
        assert data.user_id == _ID_1
        assert data.type == notifications_constants.NotificationType.ACCOUNT_SECURITY_CHANGED
        assert data.source_event_id == "event-1"
        assert data.options == {"change": "password_changed"}
        assert ws_message == notifications_constants.ACCOUNT_SECURITY_CHANGED_WS_MESSAGE
        assert created is True
        mock_db.commit.assert_called_once()

    def test_an_unlink_records_the_provider(self, mock_db):
        idp = MagicMock()
        idp.name = "Authentik"

        _, create_once = _create(mock_db, "identity_provider_unlinked", IDP_ID, idp)

        assert create_once.call_args.args[0].options == {
            "change": "identity_provider_unlinked",
            "idp_id": str(IDP_ID),
            "idp_name": "Authentik",
        }

    def test_an_unlink_of_a_deleted_provider_leaves_the_name_empty(self, mock_db):
        _, create_once = _create(mock_db, "identity_provider_unlinked", IDP_ID, None)

        assert create_once.call_args.args[0].options == {
            "change": "identity_provider_unlinked",
            "idp_id": str(IDP_ID),
            "idp_name": None,
        }

    def test_requires_the_user(self, mock_db):
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=None),
            patch("modules.notifications.service.notifications_crud.create_notification_once") as create_once,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            notifications_service.create_account_security_changed_notification(_ID_1, "mfa_enabled", None, "e", mock_db)
        create_once.assert_not_called()

    def test_a_redelivered_event_reports_not_created(self, mock_db):
        (_, _, created), _ = _create(mock_db, "mfa_enabled", created=False)

        assert created is False


class TestNotifyAccountSecurityChangedForEvent:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_creates_notification_and_pushes(self, mock_notif, _db, mock_ws):
        mock_notif.create_account_security_changed_notification.return_value = (
            MagicMock(id=uuid.UUID(int=5)),
            "WS",
            True,
        )
        event = _event("identity_provider_unlinked", IDP_ID)

        notification_subscribers.notify_account_security_changed_for_event(event)

        assert mock_notif.create_account_security_changed_notification.call_args.args[:4] == (
            _ID_1,
            account_security_events.AccountSecurityChange.IDENTITY_PROVIDER_UNLINKED,
            IDP_ID,
            event.event_id,
        )
        mock_ws.push_to_user.assert_called_once()

    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_skips_push_for_a_duplicate_event(self, mock_notif, _db, mock_ws):
        mock_notif.create_account_security_changed_notification.return_value = (
            MagicMock(id=uuid.UUID(int=5)),
            "WS",
            False,
        )

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


class TestNotifyPasswordResetCompletedForEvent:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_creates_the_password_reset_notification(self, mock_notif, _db, mock_ws):
        mock_notif.create_account_security_changed_notification.return_value = (
            MagicMock(id=uuid.UUID(int=5)),
            "WS",
            True,
        )
        event = new_event(password_reset_events.PASSWORD_RESET_COMPLETED, {"user_id": str(_ID_1)}, source="test")

        notification_subscribers.notify_password_reset_completed_for_event(event)

        assert mock_notif.create_account_security_changed_notification.call_args.args[:4] == (
            _ID_1,
            "password_reset",
            None,
            event.event_id,
        )
        mock_ws.push_to_user.assert_called_once()

    def test_an_outbox_event_published_as_an_account_security_change_is_still_handled(self):
        with (
            patch("modules.notifications.integration_service.websocket_integration"),
            patch("modules.notifications.subscribers.core_database"),
            patch("modules.notifications.subscribers.notifications_service") as mock_notif,
        ):
            mock_notif.create_account_security_changed_notification.return_value = (
                MagicMock(id=uuid.UUID(int=5)),
                "WS",
                True,
            )
            notification_subscribers.notify_account_security_changed_for_event(_event("password_reset"))

        assert mock_notif.create_account_security_changed_notification.call_args.args[1] == "password_reset"

    def test_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)

        assert any(c.args[0] == password_reset_events.PASSWORD_RESET_COMPLETED for c in events.subscribe.call_args_list)
        assert any(
            c.args[:2] == (password_reset_events.PASSWORD_RESET_COMPLETED, "auth.notify_password_reset_completed")
            for c in registry.register.call_args_list
        )


class TestNotifyMfaLockedForEvent:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_creates_the_mfa_locked_notification(self, mock_notif, _db, mock_ws):
        mock_notif.create_account_security_changed_notification.return_value = (
            MagicMock(id=uuid.UUID(int=5)),
            "WS",
            True,
        )
        event = new_event(authentication_events.MFA_LOCKED, {"user_id": str(_ID_1)}, source="test")

        notification_subscribers.notify_mfa_locked_for_event(event)

        assert mock_notif.create_account_security_changed_notification.call_args.args[:4] == (
            _ID_1,
            "mfa_locked",
            None,
            event.event_id,
        )
        mock_ws.push_to_user.assert_called_once()

    def test_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)

        assert any(c.args[0] == authentication_events.MFA_LOCKED for c in events.subscribe.call_args_list)
        assert any(
            c.args[:2] == (authentication_events.MFA_LOCKED, "auth.notify_mfa_locked")
            for c in registry.register.call_args_list
        )


class TestNotifyStepUpForEvent:
    @pytest.mark.parametrize(
        ("channel", "change", "handler", "subscriber_id"),
        [
            (
                account_security_events.STEP_UP_SESSION_ENDED,
                "step_up_session_ended",
                "notify_step_up_session_ended_for_event",
                "auth.notify_step_up_session_ended",
            ),
            (
                account_security_events.STEP_UP_LOCKED,
                "step_up_locked",
                "notify_step_up_locked_for_event",
                "auth.notify_step_up_locked",
            ),
        ],
    )
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_creates_the_notification_and_is_registered(
        self, mock_notif, _db, mock_ws, channel, change, handler, subscriber_id
    ):
        mock_notif.create_account_security_changed_notification.return_value = (
            MagicMock(id=uuid.UUID(int=5)),
            "WS",
            True,
        )
        event = new_event(channel, {"user_id": str(_ID_1)}, source="test")

        getattr(notification_subscribers, handler)(event)

        assert mock_notif.create_account_security_changed_notification.call_args.args[:4] == (
            _ID_1,
            change,
            None,
            event.event_id,
        )
        mock_ws.push_to_user.assert_called_once()
        events = MagicMock()
        registry = MagicMock()
        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)
        assert any(c.args[0] == channel for c in events.subscribe.call_args_list)
        assert any(c.args[:2] == (channel, subscriber_id) for c in registry.register.call_args_list)


class TestNotifyAccountLockedForEvent:
    @patch("modules.notifications.integration_service.websocket_integration")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_service")
    def test_creates_the_account_locked_notification(self, mock_notif, _db, mock_ws):
        mock_notif.create_account_security_changed_notification.return_value = (
            MagicMock(id=uuid.UUID(int=5)),
            "WS",
            True,
        )
        event = new_event(authentication_events.ACCOUNT_LOCKED, {"user_id": str(_ID_1)}, source="test")

        notification_subscribers.notify_account_locked_for_event(event)

        assert mock_notif.create_account_security_changed_notification.call_args.args[:4] == (
            _ID_1,
            "account_locked",
            None,
            event.event_id,
        )
        mock_ws.push_to_user.assert_called_once()

    def test_is_registered_on_the_bus_and_as_a_durable_handler(self):
        events = MagicMock()
        registry = MagicMock()

        notification_subscribers.register_bus_subscribers(events)
        notification_subscribers.register_durable_handlers(registry)

        assert any(c.args[0] == authentication_events.ACCOUNT_LOCKED for c in events.subscribe.call_args_list)
        assert any(
            c.args[:2] == (authentication_events.ACCOUNT_LOCKED, "auth.notify_account_locked")
            for c in registry.register.call_args_list
        )
