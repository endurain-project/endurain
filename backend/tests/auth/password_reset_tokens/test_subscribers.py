"""Tests for the password reset email event subscriber and publisher."""

from unittest.mock import MagicMock, patch

import jasil.events as platform_events
import jasil.providers as platform_providers
import pytest

import modules.auth.password_reset_tokens.event_publishers as password_reset_tokens_event_publishers
import modules.auth.password_reset_tokens.events as password_reset_tokens_events
import modules.auth.password_reset_tokens.subscribers as password_reset_tokens_subscribers


def _event() -> platform_events.Event:
    return platform_events.new_event(
        password_reset_tokens_events.PASSWORD_RESET_REQUESTED, {"user_id": 4}, source="test"
    )


@pytest.fixture
def session_local():
    with patch("modules.auth.password_reset_tokens.subscribers.core_database.SessionLocal") as session_local:
        yield session_local


@pytest.fixture
def mail():
    platform = MagicMock()
    with patch(
        "modules.auth.password_reset_tokens.subscribers.platform_runtime.get_active_platform", return_value=platform
    ):
        yield platform.mail


class TestHandler:
    @patch(
        "modules.auth.password_reset_tokens.subscribers.password_reset_tokens_utils.send_password_reset_email_to_user"
    )
    def test_sends_to_payload_user(self, mock_send, session_local, mail):
        password_reset_tokens_subscribers.send_password_reset_email_for_event(_event())

        mock_send.assert_called_once_with(4, mail, session_local.return_value.__enter__.return_value)

    @patch(
        "modules.auth.password_reset_tokens.subscribers.password_reset_tokens_utils.send_password_reset_email_to_user"
    )
    def test_durable_handler_raises_but_bus_subscriber_swallows(self, mock_send, session_local, mail):
        mock_send.side_effect = platform_providers.MailError("unreachable")

        with pytest.raises(platform_providers.MailError):
            password_reset_tokens_subscribers.send_password_reset_email_for_event(_event())

        password_reset_tokens_subscribers.on_password_reset_requested(_event())


class TestPublisher:
    @patch("modules.auth.password_reset_tokens.event_publishers.platform_publisher.publish")
    def test_payload_carries_user_id_only(self, mock_publish):
        db = MagicMock()

        password_reset_tokens_event_publishers.publish_password_reset_requested(4, db)

        assert mock_publish.call_args.args[1] == {"user_id": 4}
        assert mock_publish.call_args.kwargs["db"] is db
