"""The mails the sign-up module sends: who gets them, with which link, and what a redelivery or a failure does."""

import uuid

import jasil.events as platform_events
import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import MailError

import core.config as core_config
import core.exceptions as core_exceptions
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.auth.sign_up_tokens.integration_service as sign_up_integration
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.subscriber_registry as sign_up_subscriber_registry
import modules.auth.sign_up_tokens.subscribers as sign_up_subscribers
from tests._factories.mail import configure_mail, events, outbox, token_in
from tests._factories.server_settings import edit_mail_settings, edit_server_settings
from tests._factories.users import make_admin, make_sign_up, make_user

_PUBLIC = f"{core_config.ROOT_PATH}/public"
_LOGIN = f"{core_config.ROOT_PATH}/auth/login"
_PASSWORD = "A long invited passphrase 2026!"


@pytest.fixture
def mail_on(committed_sessions):
    """Mail is configured and the sign-up mail subscribers listen on the bus."""
    configure_mail(committed_sessions)
    sign_up_subscriber_registry.register_bus_subscribers(events())


def _event(event_type: str, **payload: object) -> platform_events.Event:
    return platform_events.new_event(event_type, {k: str(v) for k, v in payload.items()}, source="test")


def _tokens(committed_sessions, user_id) -> list[sign_up_models.SignUpToken]:
    with committed_sessions() as db:
        return list(
            db.scalars(
                sa.select(sign_up_models.SignUpToken)
                .where(sign_up_models.SignUpToken.user_id == user_id)
                .order_by(sign_up_models.SignUpToken.created_at)
            )
        )


class TestAdminInvitation:
    def _invite(self, committed_sessions, **fields):
        with committed_sessions() as db:
            user = make_user(db, with_password=False, **fields)
            sign_up_integration.request_admin_invitation_email(user.id, db)
            db.commit()
        return user

    def test_the_account_is_mailed_a_link_that_lets_it_choose_its_password(self, client, committed_sessions, mail_on):
        with committed_sessions() as db:
            edit_server_settings(db, signup_require_email_verification=False)
            db.commit()
        user = self._invite(committed_sessions)

        (message,) = outbox()
        assert message.to == [user.email]
        assert message.subject == "Endurain - An administrator created your account"
        confirm = client.post(f"{_PUBLIC}/sign-up/confirm", json={"token": token_in(message), "password": _PASSWORD})
        assert (confirm.status_code, confirm.json()) == (200, {"next_step": "sign_in"})
        login = client.post(
            _LOGIN, data={"username": user.username, "password": _PASSWORD}, headers={"X-Client-Type": "web"}
        )
        assert login.status_code == 200

    def test_the_mail_is_in_the_accounts_language_and_escapes_its_name(self, committed_sessions, mail_on):
        self._invite(committed_sessions, preferred_language="pt-PT", name="<b>Bo</b>")

        (message,) = outbox()
        assert 'lang="pt-PT"' in (message.html or "")
        assert "<b>Bo</b>" not in (message.html or "")

    def test_without_a_mail_server_the_request_is_refused_and_nothing_is_staged(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db, with_password=False)
            with pytest.raises(core_exceptions.ServiceUnavailableError):
                sign_up_integration.request_admin_invitation_email(user.id, db)
        assert outbox() == []


class TestApprovalMails:
    def test_every_active_administrator_is_asked_once_and_nobody_else(self, committed_sessions, mail_on):
        with committed_sessions() as db:
            first, second, regular = make_admin(db), make_admin(db), make_user(db)
            pending = make_sign_up(db, pending_admin_approval=True, with_password=False)
            assert sign_up_integration.request_sign_up_admin_approval(pending.id, db) is True
            db.commit()

        assert sorted(message.to[0] for message in outbox()) == sorted([first.email, second.email])
        assert {message.subject for message in outbox()} == {"Endurain - New user sign-up pending approval"}
        assert regular.email not in [to for message in outbox() for to in message.to]

    def test_without_a_mail_server_no_request_is_staged(self, committed_sessions):
        with committed_sessions() as db:
            make_admin(db)
            pending = make_sign_up(db, pending_admin_approval=True)
            assert sign_up_integration.request_sign_up_admin_approval(pending.id, db) is False
            db.commit()
        assert outbox() == []

    def test_the_approved_account_is_told(self, committed_sessions, mail_on):
        with committed_sessions() as db:
            user = make_user(db)
            assert sign_up_integration.request_sign_up_approved_email(user.id, db) is True
            db.commit()

        (message,) = outbox()
        assert (message.to, message.subject) == ([user.email], "Endurain - Your account has been approved")

    def test_without_a_mail_server_the_approval_notice_is_not_staged(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            assert sign_up_integration.request_sign_up_approved_email(user.id, db) is False
            db.commit()
        assert outbox() == []


class TestRedelivery:
    def test_a_redelivered_verification_event_mails_the_same_link_and_keeps_one_token(
        self, committed_sessions, mail_on
    ):
        with committed_sessions() as db:
            user = make_sign_up(db, with_password=False)
            db.commit()
        event = _event(sign_up_events.SIGN_UP_VERIFICATION_REQUESTED, user_id=user.id)

        sign_up_subscribers.send_verification_email_for_event(event)
        sign_up_subscribers.send_verification_email_for_event(event)

        first, second = outbox()
        assert token_in(first) == token_in(second)
        assert [token.used for token in _tokens(committed_sessions, user.id)] == [False]

    def test_a_new_request_replaces_the_earlier_link_and_a_retry_of_the_old_one_does_not_revoke_the_new(
        self, client, committed_sessions, mail_on
    ):
        with committed_sessions() as db:
            edit_server_settings(db, signup_enabled=True, signup_require_email_verification=True)
            user = make_sign_up(db, with_password=False)
            db.commit()
        older = _event(sign_up_events.SIGN_UP_VERIFICATION_REQUESTED, user_id=user.id)
        newer = _event(sign_up_events.SIGN_UP_VERIFICATION_REQUESTED, user_id=user.id)
        sign_up_subscribers.send_verification_email_for_event(older)
        sign_up_subscribers.send_verification_email_for_event(newer)

        sign_up_subscribers.send_verification_email_for_event(older)

        first, second, retried = outbox()
        assert token_in(first) != token_in(second)
        assert token_in(retried) == token_in(first)
        assert [token.used for token in _tokens(committed_sessions, user.id)] == [True, False]
        stale = client.post(f"{_PUBLIC}/sign-up/confirm", json={"token": token_in(first), "password": _PASSWORD})
        fresh = client.post(f"{_PUBLIC}/sign-up/confirm", json={"token": token_in(second), "password": _PASSWORD})
        assert (stale.status_code, fresh.status_code) == (400, 200)


_USER_EVENTS = [
    pytest.param(
        sign_up_events.SIGN_UP_VERIFICATION_REQUESTED,
        sign_up_subscribers.send_verification_email_for_event,
        id="verify",
    ),
    pytest.param(
        sign_up_events.ADMIN_INVITATION_REQUESTED,
        sign_up_subscribers.send_admin_invitation_email_for_event,
        id="invite",
    ),
    pytest.param(
        sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
        sign_up_subscribers.send_email_change_verification_email_for_event,
        id="change-verification",
    ),
    pytest.param(
        sign_up_events.EMAIL_CHANGE_REQUESTED,
        sign_up_subscribers.send_email_change_requested_email_for_event,
        id="change-requested",
    ),
    pytest.param(sign_up_events.SIGN_UP_APPROVED, sign_up_subscribers.send_approved_email_for_event, id="approved"),
    pytest.param(
        sign_up_events.SIGN_UP_EXISTING_ACCOUNT,
        sign_up_subscribers.send_existing_account_email_for_event,
        id="existing-account",
    ),
    pytest.param(
        sign_up_events.EMAIL_CHANGE_ADDRESS_TAKEN,
        sign_up_subscribers.send_email_change_address_taken_email_for_event,
        id="address-taken",
    ),
]


class TestEventsForRecordsThatAreGone:
    @pytest.mark.parametrize(("event_type", "handler"), _USER_EVENTS)
    def test_an_event_for_a_deleted_user_mails_nobody(self, committed_sessions, mail_on, event_type, handler):
        handler(_event(event_type, user_id=uuid.uuid4()))

        assert outbox() == []

    def test_an_approval_request_for_a_deleted_user_or_administrator_mails_nobody(self, committed_sessions, mail_on):
        with committed_sessions() as db:
            admin, user = make_admin(db), make_user(db)
            db.commit()

        sign_up_subscribers.send_approval_request_email_for_event(
            _event(sign_up_events.SIGN_UP_APPROVAL_REQUESTED, user_id=uuid.uuid4(), admin_user_id=admin.id)
        )
        sign_up_subscribers.send_approval_request_email_for_event(
            _event(sign_up_events.SIGN_UP_APPROVAL_REQUESTED, user_id=user.id, admin_user_id=uuid.uuid4())
        )

        assert outbox() == []

    def test_an_email_changed_event_for_a_missing_row_mails_nobody(self, committed_sessions, mail_on):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()

        sign_up_subscribers.send_email_changed_email_for_event(
            _event(sign_up_events.EMAIL_CHANGED, user_id=user.id, token_id=uuid.uuid4())
        )

        assert outbox() == []


class TestDeliveryFailures:
    def _refuse(self, monkeypatch, status):
        def refuse(_message):
            raise MailError("refused", status=status)

        monkeypatch.setattr(platform_runtime.get_active_platform().mail, "send", refuse)

    def test_a_transient_failure_fails_the_durable_run_so_it_is_retried_but_not_the_bus_one(
        self, committed_sessions, mail_on, monkeypatch
    ):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        self._refuse(monkeypatch, 421)
        event = _event(sign_up_events.SIGN_UP_APPROVED, user_id=user.id)

        with pytest.raises(MailError):
            sign_up_subscribers.send_approved_email_for_event(event)
        sign_up_subscribers.on_sign_up_approved(event)

    def test_a_permanent_refusal_is_dropped_without_failing_the_run(self, committed_sessions, mail_on, monkeypatch):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        self._refuse(monkeypatch, 550)

        sign_up_subscribers.send_approved_email_for_event(_event(sign_up_events.SIGN_UP_APPROVED, user_id=user.id))

        assert outbox() == []

    def test_a_mail_server_that_was_never_configured_drops_the_mail(self, committed_sessions, monkeypatch):
        with committed_sessions() as db:
            user = make_user(db)
            edit_mail_settings(db, host=None)
            db.commit()
        self._refuse(monkeypatch, 550)

        sign_up_subscribers.send_approved_email_for_event(_event(sign_up_events.SIGN_UP_APPROVED, user_id=user.id))


class TestSubscriberRegistration:
    def test_every_mail_event_has_a_bus_subscriber_and_one_durable_handler(self):
        registry = JobHandlerRegistry()
        sign_up_subscriber_registry.register_durable_handlers(registry)
        channels = {
            sign_up_events.SIGN_UP_VERIFICATION_REQUESTED,
            sign_up_events.ADMIN_INVITATION_REQUESTED,
            sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
            sign_up_events.EMAIL_CHANGE_REQUESTED,
            sign_up_events.EMAIL_CHANGED,
            sign_up_events.SIGN_UP_APPROVAL_REQUESTED,
            sign_up_events.SIGN_UP_APPROVED,
            sign_up_events.SIGN_UP_EXISTING_ACCOUNT,
            sign_up_events.EMAIL_CHANGE_ADDRESS_TAKEN,
        }

        assert {channel: len(registry.subscribers_for(channel)) for channel in channels} == dict.fromkeys(channels, 1)
        nets = {net.subscriber_id for net in sign_up_subscriber_registry.DURABLE_SUBSCRIBER_NETS}
        registered = {subscriber for channel in channels for subscriber in registry.subscribers_for(channel)}
        assert nets == registered
        assert all(
            net.backfill is None and net.exempt_reason for net in sign_up_subscriber_registry.DURABLE_SUBSCRIBER_NETS
        )
