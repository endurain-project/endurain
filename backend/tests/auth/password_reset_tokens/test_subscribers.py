"""Tests for the password-reset email subscriber and publisher."""

from unittest.mock import MagicMock, patch

import jasil.event_versioning as platform_event_versioning
import jasil.events as platform_events
import jasil.providers as platform_providers
import pytest

import core.event_metadata as core_event_metadata
import modules.auth.password_reset_tokens.event_publishers as password_reset_publishers
import modules.auth.password_reset_tokens.events as password_reset_events
import modules.auth.password_reset_tokens.subscribers as password_reset_subscribers

_CLIENT = {"ip_address": "203.0.113.7", "user_agent": "agent/1.0"}


def _event() -> platform_events.Event:
    return platform_events.new_event(
        password_reset_events.PASSWORD_RESET_REQUESTED,
        {"user_id": 4, **_CLIENT},
        source="test",
        schema_version=password_reset_events.PasswordResetRequestedPayload.SCHEMA_VERSION,
    )


class TestHandler:
    @patch("modules.auth.password_reset_tokens.subscribers.core_mail.send_email", return_value=True)
    @patch("modules.auth.password_reset_tokens.subscribers.password_reset_service.prepare_password_reset_email")
    @patch("modules.auth.password_reset_tokens.subscribers.core_config.settings")
    @patch("modules.auth.password_reset_tokens.subscribers.platform_runtime.get_state")
    @patch("modules.auth.password_reset_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.password_reset_tokens.subscribers.core_database.SessionLocal")
    def test_prepares_inside_session_and_sends_after_it_closes(
        self, session_local, get_platform, get_state, settings, prepare, send_email
    ):
        db = session_local.return_value.__enter__.return_value
        settings.ENDURAIN_HOST = "https://example.test"
        prepare.return_value = ("person@example.test", "subject", "<p>body</p>", "body")
        get_platform.return_value.mail = MagicMock()

        event = _event()
        password_reset_subscribers.send_password_reset_email_for_event(event)

        (payload, event_id, host, state, session) = prepare.call_args.args
        assert payload.user_id == 4
        assert (payload.ip_address, payload.user_agent) == (_CLIENT["ip_address"], _CLIENT["user_agent"])
        assert (event_id, host, state, session) == (event.event_id, "https://example.test", get_state.return_value, db)
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
    @patch("modules.auth.password_reset_tokens.subscribers.platform_runtime.get_state")
    @patch("modules.auth.password_reset_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.password_reset_tokens.subscribers.core_database.SessionLocal")
    def test_durable_handler_raises_but_bus_subscriber_swallows(
        self, _session_local, get_platform, _state, prepare, _send_email
    ):
        prepare.return_value = ("person@example.test", "subject", "html", "text")
        get_platform.return_value.mail = MagicMock()

        with pytest.raises(platform_providers.MailError):
            password_reset_subscribers.send_password_reset_email_for_event(_event())
        password_reset_subscribers.on_password_reset_requested(_event())

    @patch("modules.auth.password_reset_tokens.subscribers.core_mail.send_email")
    @patch("modules.auth.password_reset_tokens.subscribers.password_reset_service.prepare_password_reset_email")
    @patch("modules.auth.password_reset_tokens.subscribers.platform_runtime.get_state")
    @patch("modules.auth.password_reset_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.password_reset_tokens.subscribers.core_database.SessionLocal")
    def test_nothing_is_sent_when_the_service_admits_no_request(self, _session, _platform, _state, prepare, send_email):
        prepare.return_value = None

        password_reset_subscribers.send_password_reset_email_for_event(_event())

        send_email.assert_not_called()


class TestPayloadVersioning:
    def test_a_queued_v1_event_is_upgraded_with_no_client_data(self):
        event = platform_events.new_event(
            password_reset_events.PASSWORD_RESET_REQUESTED, {"user_id": 4}, source="test", schema_version=1
        )

        payload = platform_event_versioning.parse_payload(password_reset_events.PasswordResetRequestedPayload, event)

        assert (payload.user_id, payload.ip_address, payload.user_agent) == (4, None, None)

    def test_the_current_version_is_two(self):
        assert password_reset_events.PasswordResetRequestedPayload.SCHEMA_VERSION == 2


class TestPublisher:
    @patch("modules.auth.password_reset_tokens.event_publishers.platform_publisher.publish_on_commit")
    def test_payload_carries_user_id_and_client_only(self, mock_publish):
        db = MagicMock()

        password_reset_publishers.publish_password_reset_requested(4, "203.0.113.7", "agent/1.0", db)

        assert mock_publish.call_args.args[1] == {"user_id": 4, "ip_address": "203.0.113.7", "user_agent": "agent/1.0"}
        assert mock_publish.call_args.kwargs["db"] is db
        assert mock_publish.call_args.kwargs["schema_version"] == 2
        assert mock_publish.call_args.kwargs["metadata"] == {core_event_metadata.META_USER_ID: 4}

    @patch("modules.auth.password_reset_tokens.event_publishers.platform_publisher.publish_on_commit")
    def test_an_unknown_address_has_no_user_id_and_no_user_metadata(self, mock_publish):
        password_reset_publishers.publish_password_reset_requested(None, "203.0.113.7", "agent/1.0", MagicMock())

        assert mock_publish.call_args.args[1]["user_id"] is None
        assert mock_publish.call_args.kwargs["metadata"] == {}

    @patch("modules.auth.password_reset_tokens.event_publishers.platform_publisher.publish")
    @patch("modules.auth.password_reset_tokens.event_publishers.platform_publisher.publish_on_commit")
    def test_stages_in_the_callers_transaction_without_committing(self, mock_staged, mock_bare):
        db = MagicMock()

        password_reset_publishers.publish_password_reset_requested(4, None, None, db)

        mock_bare.assert_not_called()
        mock_staged.assert_called_once()
        db.commit.assert_not_called()


class TestCompletedPublisher:
    @patch("modules.auth.password_reset_tokens.event_publishers.platform_publisher.publish_on_commit")
    def test_stages_the_completed_event_with_the_user_id_only(self, mock_publish):
        db = MagicMock()

        password_reset_publishers.publish_password_reset_completed(4, db)

        assert mock_publish.call_args.args[0] == "auth.password_reset_completed"
        assert mock_publish.call_args.args[1] == {"user_id": 4}
        assert mock_publish.call_args.kwargs["db"] is db
        db.commit.assert_not_called()
