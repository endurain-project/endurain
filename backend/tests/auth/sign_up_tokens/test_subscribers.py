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

        sign_up_subscribers.send_verification_email_for_event(
            _event(sign_up_events.SIGN_UP_VERIFICATION_REQUESTED, {"user_id": 4})
        )

        prepare.assert_called_once_with(4, sign_up_subscribers.core_config.settings.ENDURAIN_HOST, db)
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
    @patch("modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish")
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
    def test_approval_is_staged_for_the_callers_commit(self, mock_publish):
        db = MagicMock()

        sign_up_publishers.publish_sign_up_approved(4, db)

        assert mock_publish.call_args.args[1] == {"user_id": 4}
        assert mock_publish.call_args.kwargs["db"] is db
        assert "commit" not in mock_publish.call_args.kwargs
