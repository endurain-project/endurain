"""Tests for the sign-up email event subscribers and publishers."""

from unittest.mock import MagicMock, patch

import jasil.events as platform_events
import jasil.providers as platform_providers
import pytest

import modules.auth.sign_up_tokens.event_publishers as sign_up_tokens_event_publishers
import modules.auth.sign_up_tokens.events as sign_up_tokens_events
import modules.auth.sign_up_tokens.subscribers as sign_up_tokens_subscribers


def _event(event_type: str, payload: dict) -> platform_events.Event:
    return platform_events.new_event(event_type, payload, source="test")


@pytest.fixture
def session_local():
    with patch("modules.auth.sign_up_tokens.subscribers.core_database.SessionLocal") as session_local:
        yield session_local


@pytest.fixture
def mail():
    platform = MagicMock()
    with patch("modules.auth.sign_up_tokens.subscribers.platform_runtime.get_active_platform", return_value=platform):
        yield platform.mail


class TestHandlers:
    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_tokens_utils.send_sign_up_verification_email_to_user")
    def test_verification_handler_sends_to_payload_user(self, mock_send, session_local, mail):
        event = _event(sign_up_tokens_events.SIGN_UP_VERIFICATION_REQUESTED, {"user_id": 4})

        sign_up_tokens_subscribers.send_verification_email_for_event(event)

        mock_send.assert_called_once_with(4, mail, session_local.return_value.__enter__.return_value)

    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_tokens_utils.send_sign_up_approval_request_email_to_admin")
    def test_approval_request_handler_targets_admin(self, mock_send, session_local, mail):
        event = _event(sign_up_tokens_events.SIGN_UP_APPROVAL_REQUESTED, {"user_id": 4, "admin_user_id": 9})

        sign_up_tokens_subscribers.send_approval_request_email_for_event(event)

        mock_send.assert_called_once_with(4, 9, mail, session_local.return_value.__enter__.return_value)

    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_tokens_utils.send_sign_up_approved_email_to_user")
    def test_approved_handler_sends_to_payload_user(self, mock_send, session_local, mail):
        event = _event(sign_up_tokens_events.SIGN_UP_APPROVED, {"user_id": 4})

        sign_up_tokens_subscribers.send_approved_email_for_event(event)

        mock_send.assert_called_once_with(4, mail, session_local.return_value.__enter__.return_value)

    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_tokens_utils.send_sign_up_approved_email_to_user")
    def test_durable_handler_raises_but_bus_subscriber_swallows(self, mock_send, session_local, mail):
        mock_send.side_effect = platform_providers.MailError("unreachable")
        event = _event(sign_up_tokens_events.SIGN_UP_APPROVED, {"user_id": 4})

        with pytest.raises(platform_providers.MailError):
            sign_up_tokens_subscribers.send_approved_email_for_event(event)

        sign_up_tokens_subscribers.on_sign_up_approved(event)


class TestPublishers:
    @patch("modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish")
    def test_payloads_carry_ids_only(self, mock_publish):
        db = MagicMock()

        sign_up_tokens_event_publishers.publish_sign_up_verification_requested(4, db)
        sign_up_tokens_event_publishers.publish_sign_up_approval_requested(4, 9, db)
        sign_up_tokens_event_publishers.publish_sign_up_approved(4, db)

        payloads = [call.args[1] for call in mock_publish.call_args_list]
        assert payloads == [{"user_id": 4}, {"user_id": 4, "admin_user_id": 9}, {"user_id": 4}]
        assert all(call.kwargs["db"] is db for call in mock_publish.call_args_list)
