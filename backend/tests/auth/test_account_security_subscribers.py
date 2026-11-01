"""Tests for the account-security email service function and subscribers."""

from unittest.mock import MagicMock, patch

import jasil.events as platform_events
import jasil.providers as platform_providers
import pytest

import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.subscribers as account_security_subscribers
import modules.auth.identity_providers.events as idp_events

SERVICE = "modules.auth.account_security.account_security_service"
SUBSCRIBERS = "modules.auth.account_security.subscribers"
HOST = "https://endurain.example.com"


def _user(active=True):
    user = MagicMock()
    user.name = "Alice"
    user.email = "alice@example.test"
    user.preferred_language = "en"
    user.active = active
    return user


class TestPrepareSecurityChangeEmail:
    @pytest.mark.parametrize("change", [change.value for change in account_security_events.AccountSecurityChange])
    def test_prepares_a_message_for_each_change(self, change, mock_db):
        with (
            patch(f"{SERVICE}.users_integration.get_user", return_value=_user()),
            patch(f"{SERVICE}.identity_providers_integration.get_identity_provider", return_value=None),
        ):
            message = account_security_service.prepare_security_change_email(1, change, None, HOST, mock_db)

        assert message is not None
        recipient, subject, html_body, text_body = message
        assert recipient == "alice@example.test"
        assert subject and html_body and text_body

    def test_an_unlink_names_the_provider(self, mock_db):
        idp = MagicMock()
        idp.name = "Authentik"
        with (
            patch(f"{SERVICE}.users_integration.get_user", return_value=_user()),
            patch(f"{SERVICE}.identity_providers_integration.get_identity_provider", return_value=idp) as get_idp,
        ):
            message = account_security_service.prepare_security_change_email(
                1, "identity_provider_unlinked", 4, HOST, mock_db
            )

        get_idp.assert_called_once_with(4, mock_db)
        assert "Authentik" in message[2]

    def test_a_deleted_provider_leaves_the_name_out(self, mock_db):
        with (
            patch(f"{SERVICE}.users_integration.get_user", return_value=_user()),
            patch(f"{SERVICE}.identity_providers_integration.get_identity_provider", return_value=None),
        ):
            message = account_security_service.prepare_security_change_email(
                1, "identity_provider_unlinked", 4, HOST, mock_db
            )

        assert message is not None
        assert "None" not in message[2]

    def test_a_missing_user_sends_nothing(self, mock_db):
        with patch(f"{SERVICE}.users_integration.get_user", return_value=None):
            assert account_security_service.prepare_security_change_email(1, "mfa_enabled", None, HOST, mock_db) is None

    def test_an_inactive_user_sends_nothing(self, mock_db):
        with patch(f"{SERVICE}.users_integration.get_user", return_value=_user(active=False)):
            assert account_security_service.prepare_security_change_email(1, "mfa_enabled", None, HOST, mock_db) is None


def _changed_event(change, idp_id=None):
    payload = {"user_id": 4, "change": change}
    if idp_id is not None:
        payload["idp_id"] = idp_id
    return platform_events.new_event(account_security_events.ACCOUNT_SECURITY_CHANGED, payload, source="test")


class TestSecurityChangedHandler:
    @patch(f"{SUBSCRIBERS}.core_mail.send_email", return_value=True)
    @patch(f"{SUBSCRIBERS}.account_security_service.prepare_security_change_email")
    @patch(f"{SUBSCRIBERS}.platform_runtime.get_active_platform")
    @patch(f"{SUBSCRIBERS}.core_database.SessionLocal")
    def test_prepares_in_a_session_and_sends_afterward(self, session_local, get_platform, prepare, send_email):
        db = session_local.return_value.__enter__.return_value
        prepare.return_value = ("alice@example.test", "subject", "html", "text")

        account_security_subscribers.send_security_changed_email_for_event(
            _changed_event("identity_provider_unlinked", 7)
        )

        prepare.assert_called_once_with(
            4, "identity_provider_unlinked", 7, account_security_subscribers.core_config.settings.ENDURAIN_HOST, db
        )
        session_local.return_value.__exit__.assert_called_once()
        send_email.assert_called_once_with(get_platform.return_value.mail, *prepare.return_value)

    @patch(f"{SUBSCRIBERS}.core_mail.send_email")
    @patch(f"{SUBSCRIBERS}.account_security_service.prepare_security_change_email", return_value=None)
    @patch(f"{SUBSCRIBERS}.platform_runtime.get_active_platform")
    @patch(f"{SUBSCRIBERS}.core_database.SessionLocal")
    def test_a_missing_user_sends_nothing(self, _session_local, _get_platform, _prepare, send_email):
        account_security_subscribers.send_security_changed_email_for_event(_changed_event("mfa_enabled"))

        send_email.assert_not_called()

    @patch(
        f"{SUBSCRIBERS}.core_mail.send_email",
        side_effect=platform_providers.MailError("Mail delivery failed"),
    )
    @patch(f"{SUBSCRIBERS}.account_security_service.prepare_security_change_email")
    @patch(f"{SUBSCRIBERS}.platform_runtime.get_active_platform")
    @patch(f"{SUBSCRIBERS}.core_database.SessionLocal")
    def test_the_durable_handler_raises_a_transient_mail_failure(self, _session_local, _platform, prepare, _send):
        prepare.return_value = ("alice@example.test", "subject", "html", "text")

        with pytest.raises(platform_providers.MailError):
            account_security_subscribers.send_security_changed_email_for_event(_changed_event("mfa_enabled"))


class TestIdpLinkedHandler:
    @patch(f"{SUBSCRIBERS}.core_mail.send_email", return_value=True)
    @patch(f"{SUBSCRIBERS}.account_security_service.prepare_security_change_email")
    @patch(f"{SUBSCRIBERS}.platform_runtime.get_active_platform")
    @patch(f"{SUBSCRIBERS}.core_database.SessionLocal")
    def test_prepares_a_link_message_and_sends_it(self, session_local, get_platform, prepare, send_email):
        db = session_local.return_value.__enter__.return_value
        prepare.return_value = ("alice@example.test", "subject", "html", "text")
        event = platform_events.new_event(idp_events.IDP_LINKED, {"user_id": 4, "idp_id": 7}, source="test")

        account_security_subscribers.send_idp_linked_email_for_event(event)

        prepare.assert_called_once_with(
            4, "identity_provider_linked", 7, account_security_subscribers.core_config.settings.ENDURAIN_HOST, db
        )
        send_email.assert_called_once_with(get_platform.return_value.mail, *prepare.return_value)


class TestRegistration:
    def test_both_events_are_registered_on_the_bus_and_as_durable_handlers_with_distinct_ids(self):
        events = MagicMock()
        registry = MagicMock()

        account_security_subscribers.register_bus_subscribers(events)
        account_security_subscribers.register_durable_handlers(registry)

        events.subscribe.assert_any_call(
            account_security_events.ACCOUNT_SECURITY_CHANGED, account_security_subscribers.on_security_changed
        )
        events.subscribe.assert_any_call(idp_events.IDP_LINKED, account_security_subscribers.on_idp_linked)
        registry.register.assert_any_call(
            account_security_events.ACCOUNT_SECURITY_CHANGED,
            "auth.send_account_security_changed_email",
            account_security_subscribers.send_security_changed_email_for_event,
        )
        registry.register.assert_any_call(
            idp_events.IDP_LINKED,
            "auth.send_idp_linked_email",
            account_security_subscribers.send_idp_linked_email_for_event,
        )
