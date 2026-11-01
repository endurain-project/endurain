"""Tests for the password-reset email subscriber and publisher."""

from unittest.mock import MagicMock, patch

import jasil.events as platform_events
import jasil.providers as platform_providers
import pytest

import modules.auth.password_reset_tokens.event_publishers as password_reset_publishers
import modules.auth.password_reset_tokens.events as password_reset_events
import modules.auth.password_reset_tokens.subscribers as password_reset_subscribers


def _event() -> platform_events.Event:
    return platform_events.new_event(password_reset_events.PASSWORD_RESET_REQUESTED, {"user_id": 4}, source="test")


class TestHandler:
    @patch("modules.auth.password_reset_tokens.subscribers.core_mail.send_email", return_value=True)
    @patch("modules.auth.password_reset_tokens.subscribers.password_reset_service.prepare_password_reset_email")
    @patch("modules.auth.password_reset_tokens.subscribers.core_config.settings")
    @patch("modules.auth.password_reset_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.password_reset_tokens.subscribers.core_database.SessionLocal")
    def test_prepares_inside_session_and_sends_after_it_closes(
        self, session_local, get_platform, settings, prepare, send_email
    ):
        db = session_local.return_value.__enter__.return_value
        settings.ENDURAIN_HOST = "https://example.test"
        prepare.return_value = ("person@example.test", "subject", "<p>body</p>", "body")
        get_platform.return_value.mail = MagicMock()

        event = _event()
        password_reset_subscribers.send_password_reset_email_for_event(event)

        prepare.assert_called_once_with(4, event.event_id, "https://example.test", db)
        session_local.return_value.__exit__.assert_called_once()
        send_email.assert_called_once_with(
            get_platform.return_value.mail,
            "person@example.test",
            "subject",
            "<p>body</p>",
            "body",
        )

    @patch(
        "modules.auth.password_reset_tokens.subscribers.core_mail.send_email",
        side_effect=platform_providers.MailError("Mail delivery failed"),
    )
    @patch("modules.auth.password_reset_tokens.subscribers.password_reset_service.prepare_password_reset_email")
    @patch("modules.auth.password_reset_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.password_reset_tokens.subscribers.core_database.SessionLocal")
    def test_durable_handler_raises_but_bus_subscriber_swallows(
        self, _session_local, get_platform, prepare, _send_email
    ):
        prepare.return_value = ("person@example.test", "subject", "html", "text")
        get_platform.return_value.mail = MagicMock()

        with pytest.raises(platform_providers.MailError):
            password_reset_subscribers.send_password_reset_email_for_event(_event())
        password_reset_subscribers.on_password_reset_requested(_event())


class TestPublisher:
    @patch("modules.auth.password_reset_tokens.event_publishers.platform_publisher.publish_on_commit")
    def test_payload_carries_user_id_only(self, mock_publish):
        db = MagicMock()

        password_reset_publishers.publish_password_reset_requested(4, db)

        assert mock_publish.call_args.args[1] == {"user_id": 4}
        assert mock_publish.call_args.kwargs["db"] is db

    @patch("modules.auth.password_reset_tokens.event_publishers.platform_publisher.publish")
    @patch("modules.auth.password_reset_tokens.event_publishers.platform_publisher.publish_on_commit")
    def test_stages_in_the_callers_transaction_without_committing(self, mock_staged, mock_bare):
        db = MagicMock()

        password_reset_publishers.publish_password_reset_requested(4, db)

        mock_bare.assert_not_called()
        mock_staged.assert_called_once()
        db.commit.assert_not_called()
