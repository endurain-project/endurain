"""Tests for sign-up email subscribers and event publishers."""

from unittest.mock import MagicMock, patch

import jasil.events as platform_events
import jasil.providers as platform_providers
import pytest

import modules.auth.sign_up_tokens.event_publishers as sign_up_publishers
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.auth.sign_up_tokens.subscribers as sign_up_subscribers


def _event(event_type: str, payload: dict) -> platform_events.Event:
    return platform_events.new_event(event_type, payload, source="test")


class TestHandlers:
    @patch("modules.auth.sign_up_tokens.subscribers.core_mail.send_email", return_value=True)
    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_service.prepare_sign_up_verification_email")
    @patch("modules.auth.sign_up_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.sign_up_tokens.subscribers.core_database.SessionLocal")
    def test_verification_is_prepared_in_a_session_and_sent_afterward(
        self, session_local, get_platform, prepare, send_email
    ):
        db = session_local.return_value.__enter__.return_value
        get_platform.return_value.mail = MagicMock()
        prepare.return_value = ("person@example.test", "subject", "html", "text")

        event = _event(sign_up_events.SIGN_UP_VERIFICATION_REQUESTED, {"user_id": 4})
        sign_up_subscribers.send_verification_email_for_event(event)

        prepare.assert_called_once_with(4, event.event_id, sign_up_subscribers.core_config.settings.ENDURAIN_HOST, db)
        session_local.return_value.__exit__.assert_called_once()
        send_email.assert_called_once_with(get_platform.return_value.mail, *prepare.return_value)

    @patch(
        "modules.auth.sign_up_tokens.subscribers.core_mail.send_email",
        side_effect=platform_providers.MailError("Mail delivery failed"),
    )
    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_service.prepare_sign_up_approved_email")
    @patch("modules.auth.sign_up_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.sign_up_tokens.subscribers.core_database.SessionLocal")
    def test_durable_handler_raises_transient_mail_failure(self, _session_local, get_platform, prepare, _send_email):
        get_platform.return_value.mail = MagicMock()
        prepare.return_value = ("person@example.test", "subject", "html", "text")

        with pytest.raises(platform_providers.MailError):
            sign_up_subscribers.send_approved_email_for_event(_event(sign_up_events.SIGN_UP_APPROVED, {"user_id": 4}))


class TestEmailChangeVerificationHandler:
    @patch("modules.auth.sign_up_tokens.subscribers.core_mail.send_email", return_value=True)
    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_service.prepare_email_change_verification_email")
    @patch("modules.auth.sign_up_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.sign_up_tokens.subscribers.core_database.SessionLocal")
    def test_the_email_change_message_is_prepared_in_a_session_and_sent_afterward(
        self, session_local, get_platform, prepare, send_email
    ):
        db = session_local.return_value.__enter__.return_value
        prepare.return_value = ("new@example.test", "subject", "html", "text")

        event = _event(sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED, {"user_id": 4})
        sign_up_subscribers.send_email_change_verification_email_for_event(event)

        prepare.assert_called_once_with(4, event.event_id, sign_up_subscribers.core_config.settings.ENDURAIN_HOST, db)
        send_email.assert_called_once_with(get_platform.return_value.mail, *prepare.return_value)

    def test_both_registration_paths_route_the_event_to_its_handler(self):
        events = MagicMock()
        registry = MagicMock()

        sign_up_subscribers.register_bus_subscribers(events)
        sign_up_subscribers.register_durable_handlers(registry)

        events.subscribe.assert_any_call(
            sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
            sign_up_subscribers.on_email_change_verification_requested,
        )
        registry.register.assert_any_call(
            sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
            sign_up_subscribers.EMAIL_CHANGE_VERIFICATION_EMAIL_SUBSCRIBER_ID,
            sign_up_subscribers.send_email_change_verification_email_for_event,
        )


class TestEmailChangedHandler:
    @patch("modules.auth.sign_up_tokens.subscribers.core_mail.send_email", return_value=True)
    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_service.prepare_email_changed_email")
    @patch("modules.auth.sign_up_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.sign_up_tokens.subscribers.core_database.SessionLocal")
    def test_the_notice_is_prepared_in_a_session_and_sent_to_the_previous_address(
        self, session_local, get_platform, prepare, send_email
    ):
        db = session_local.return_value.__enter__.return_value
        prepare.return_value = ("old@example.test", "subject", "html", "text")

        sign_up_subscribers.send_email_changed_email_for_event(
            _event(sign_up_events.EMAIL_CHANGED, {"user_id": 4, "token_id": "t1"})
        )

        prepare.assert_called_once_with(4, "t1", sign_up_subscribers.core_config.settings.ENDURAIN_HOST, db)
        send_email.assert_called_once_with(
            get_platform.return_value.mail, "old@example.test", "subject", "html", "text"
        )

    @patch("modules.auth.sign_up_tokens.subscribers.core_mail.send_email")
    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_service.prepare_email_changed_email", return_value=None)
    @patch("modules.auth.sign_up_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.sign_up_tokens.subscribers.core_database.SessionLocal")
    def test_a_missing_row_is_skipped(self, _session_local, _get_platform, _prepare, send_email):
        sign_up_subscribers.send_email_changed_email_for_event(
            _event(sign_up_events.EMAIL_CHANGED, {"user_id": 4, "token_id": "t1"})
        )

        send_email.assert_not_called()

    def test_both_registration_paths_route_the_event_to_its_handler(self):
        events = MagicMock()
        registry = MagicMock()

        sign_up_subscribers.register_bus_subscribers(events)
        sign_up_subscribers.register_durable_handlers(registry)

        events.subscribe.assert_any_call(sign_up_events.EMAIL_CHANGED, sign_up_subscribers.on_email_changed)
        registry.register.assert_any_call(
            sign_up_events.EMAIL_CHANGED,
            sign_up_subscribers.EMAIL_CHANGED_EMAIL_SUBSCRIBER_ID,
            sign_up_subscribers.send_email_changed_email_for_event,
        )


class TestExistingAccountHandler:
    @patch("modules.auth.sign_up_tokens.subscribers.core_mail.send_email", return_value=True)
    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_service.prepare_sign_up_existing_account_email")
    @patch("modules.auth.sign_up_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.sign_up_tokens.subscribers.core_database.SessionLocal")
    def test_the_notice_is_prepared_in_a_session_and_sent_afterward(
        self, _session_local, get_platform, prepare, send_email
    ):
        prepare.return_value = ("owner@example.com", "subject", "<p>html</p>", "text")

        sign_up_subscribers.send_existing_account_email_for_event(
            _event(sign_up_events.SIGN_UP_EXISTING_ACCOUNT, {"user_id": 4})
        )

        assert prepare.call_args.args[0] == 4
        send_email.assert_called_once_with(
            get_platform.return_value.mail, "owner@example.com", "subject", "<p>html</p>", "text"
        )


class TestPublishers:
    @patch("modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit")
    def test_payloads_carry_ids_only(self, mock_publish):
        db = MagicMock()

        sign_up_publishers.publish_sign_up_verification_requested(4, db)
        sign_up_publishers.publish_sign_up_approval_requested(4, 9, db)
        sign_up_publishers.publish_sign_up_existing_account(5, db)

        assert [call.args[1] for call in mock_publish.call_args_list] == [
            {"user_id": 4},
            {"user_id": 4, "admin_user_id": 9},
            {"user_id": 5},
        ]
        assert all(call.kwargs["db"] is db for call in mock_publish.call_args_list)

    @patch("modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit")
    def test_email_change_events_are_staged_for_the_callers_commit_with_ids_only(self, mock_publish):
        db = MagicMock()

        sign_up_publishers.publish_email_change_verification_requested(6, db)
        sign_up_publishers.publish_email_changed(6, "token-1", db)

        assert [(call.args[0], call.args[1]) for call in mock_publish.call_args_list] == [
            (sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED, {"user_id": 6}),
            (sign_up_events.EMAIL_CHANGED, {"user_id": 6, "token_id": "token-1"}),
        ]
        assert all(call.kwargs["db"] is db for call in mock_publish.call_args_list)

    @patch("modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit")
    def test_approval_is_staged_for_the_callers_commit(self, mock_publish):
        db = MagicMock()

        sign_up_publishers.publish_sign_up_approved(4, db)

        assert mock_publish.call_args.args[1] == {"user_id": 4}
        assert mock_publish.call_args.kwargs["db"] is db
        assert "commit" not in mock_publish.call_args.kwargs
