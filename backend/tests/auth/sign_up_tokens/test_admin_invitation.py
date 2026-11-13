"""Tests for the invitation an administrator's passwordless account creation mails to the new user."""

import uuid
from unittest.mock import MagicMock, patch

import jasil.events as platform_events
import pytest
from sqlalchemy.orm import sessionmaker

import core.exceptions as core_exceptions
import modules.auth.sign_up_tokens.email_messages as email_messages
import modules.auth.sign_up_tokens.event_publishers as sign_up_publishers
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.auth.sign_up_tokens.integration_service as sign_up_integration
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.auth.sign_up_tokens.subscribers as sign_up_subscribers
import modules.users.users.models as users_models
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import create_sqlite_session, ensure_user

_OWNER_EMAIL = f"user{MOCK_USER_ID.hex}@example.com"

_USER_4 = uuid.UUID("00000000-0000-4000-8000-000000000004")
_USER_999 = uuid.UUID("00000000-0000-4000-8000-000000000999")

_SERVICE = "modules.auth.sign_up_tokens.service"
_PUBLISH = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"
_HOST = "https://app.example"


@pytest.fixture
def db():
    session = create_sqlite_session()
    factory = sessionmaker(bind=session.get_bind())
    ensure_user(factory, MOCK_USER_ID)
    session.query(users_models.Users).update({"preferred_language": "en"})
    session.commit()
    yield session
    session.close()


class TestEmail:
    def test_the_mail_says_an_administrator_created_the_account_and_carries_the_link(self):
        link = f"{_HOST}/signup/confirm?token=abc"

        subject, html_body, text_body = email_messages.get_admin_invitation_email("Alice", link, _HOST, "en")

        assert "administrator" in subject.lower()
        assert "administrator" in html_body.lower() and "administrator" in text_body.lower()
        assert link in html_body and link in text_body

    def test_the_name_is_escaped(self):
        _, html_body, _ = email_messages.get_admin_invitation_email("<img src=x>", f"{_HOST}/x", _HOST, "en")

        assert "<img src=x>" not in html_body


class TestRequest:
    @patch(_PUBLISH)
    @patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=True)
    def test_the_invitation_event_is_staged_with_the_user_id_only(self, _configured, publish):
        database = MagicMock()

        sign_up_integration.request_admin_invitation_email(MOCK_USER_ID, database)

        assert publish.call_args.args[:2] == (sign_up_events.ADMIN_INVITATION_REQUESTED, {"user_id": str(MOCK_USER_ID)})
        assert publish.call_args.kwargs["db"] is database

    @patch(_PUBLISH)
    @patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=False)
    def test_nothing_is_staged_without_mail(self, _configured, publish):
        with pytest.raises(core_exceptions.ServiceUnavailableError):
            sign_up_integration.request_admin_invitation_email(MOCK_USER_ID, MagicMock())

        publish.assert_not_called()

    @patch(_PUBLISH)
    def test_the_publisher_stages_for_the_callers_commit(self, publish):
        database = MagicMock()

        sign_up_publishers.publish_admin_invitation_requested(MOCK_USER_ID, database)

        assert publish.call_args.kwargs["db"] is database


class TestPrepare:
    def test_the_link_is_a_live_sign_up_token_and_the_mail_goes_to_the_account(self, db):
        recipient, subject, html_body, _ = sign_up_service.prepare_admin_invitation_email(
            MOCK_USER_ID, "event-1", _HOST, db
        )

        assert recipient == _OWNER_EMAIL
        assert "administrator" in subject.lower()
        token = html_body.split("/signup/confirm?token=")[1].split('"')[0].split("<")[0]
        assert sign_up_service.verify_sign_up_token(token, db, email_change=False).user_id == MOCK_USER_ID

    def test_a_retried_event_mails_the_same_link(self, db):
        first = sign_up_service.prepare_admin_invitation_email(MOCK_USER_ID, "event-1", _HOST, db)
        second = sign_up_service.prepare_admin_invitation_email(MOCK_USER_ID, "event-1", _HOST, db)

        assert first[2] == second[2]

    def test_a_missing_user_is_skipped(self, db):
        assert sign_up_service.prepare_admin_invitation_email(_USER_999, "event-1", _HOST, db) is None


class TestSubscriber:
    @patch("modules.auth.sign_up_tokens.subscribers.core_mail.send_email", return_value=True)
    @patch("modules.auth.sign_up_tokens.subscribers.sign_up_service.prepare_admin_invitation_email")
    @patch("modules.auth.sign_up_tokens.subscribers.platform_runtime.get_active_platform")
    @patch("modules.auth.sign_up_tokens.subscribers.core_database.SessionLocal")
    def test_the_invitation_is_prepared_in_a_session_and_sent_afterward(
        self, session_local, get_platform, prepare, send_email
    ):
        database = session_local.return_value.__enter__.return_value
        prepare.return_value = ("person@example.test", "subject", "html", "text")
        event = platform_events.new_event(
            sign_up_events.ADMIN_INVITATION_REQUESTED, {"user_id": str(_USER_4)}, source="test"
        )

        sign_up_subscribers.send_admin_invitation_email_for_event(event)

        prepare.assert_called_once_with(
            _USER_4, event.event_id, sign_up_subscribers.core_config.settings.ENDURAIN_HOST, database
        )
        send_email.assert_called_once_with(get_platform.return_value.mail, *prepare.return_value)

    def test_both_registration_paths_route_the_event_to_its_handler(self):
        events = MagicMock()
        registry = MagicMock()

        sign_up_subscribers.register_bus_subscribers(events)
        sign_up_subscribers.register_durable_handlers(registry)

        events.subscribe.assert_any_call(
            sign_up_events.ADMIN_INVITATION_REQUESTED, sign_up_subscribers.on_admin_invitation_requested
        )
        registry.register.assert_any_call(
            sign_up_events.ADMIN_INVITATION_REQUESTED,
            sign_up_subscribers.ADMIN_INVITATION_EMAIL_SUBSCRIBER_ID,
            sign_up_subscribers.send_admin_invitation_email_for_event,
        )
