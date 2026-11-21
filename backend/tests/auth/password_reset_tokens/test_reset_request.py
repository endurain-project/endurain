"""Requesting a password reset: the same answer for every address, one mail per admitted account."""

import logging
import uuid

import jasil.events as platform_events
import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa
from jasil.providers import MailError, StateBackendUnavailableError

import core.config as core_config
import modules.auth.password_reset_tokens.audit_actions as reset_audit_actions
import modules.auth.password_reset_tokens.events as reset_events
import modules.auth.password_reset_tokens.models as reset_models
import modules.auth.password_reset_tokens.subscriber_registry as reset_subscriber_registry
import modules.auth.password_reset_tokens.subscribers as reset_subscribers
from tests._factories.mail import configure_mail, events, outbox, token_in
from tests._factories.server_settings import edit_server_settings
from tests._factories.tokens import audit_rows
from tests._factories.users import make_admin, make_user

_PUBLIC = f"{core_config.ROOT_PATH}/public/password-reset"
_LOGIN = f"{core_config.ROOT_PATH}/auth/login"
_NEW_PASSWORD = "Another-Password-5678!"
_AGENT = "reset-test-agent/1.0"


@pytest.fixture
def mail_on(committed_sessions):
    """Mail is configured and the reset email subscriber listens on the bus."""
    configure_mail(committed_sessions)
    reset_subscriber_registry.register_bus_subscribers(events())


def _request(client, email: str):
    return client.post(f"{_PUBLIC}/request", json={"email": email}, headers={"User-Agent": _AGENT})


def _tokens(committed_sessions, user_id) -> list[reset_models.PasswordResetToken]:
    with committed_sessions() as db:
        return list(
            db.scalars(
                sa.select(reset_models.PasswordResetToken)
                .where(reset_models.PasswordResetToken.user_id == user_id)
                .order_by(reset_models.PasswordResetToken.created_at)
            )
        )


def _requests_audited(committed_sessions):
    return audit_rows(committed_sessions, reset_audit_actions.PASSWORD_RESET_REQUEST)


def _user(committed_sessions, **fields):
    with committed_sessions() as db:
        user = make_user(db, **fields)
        db.commit()
    return user


def _event(user_id: uuid.UUID | None, *, version: int = 2, **client: str | None) -> platform_events.Event:
    payload: dict[str, str | None] = {"user_id": None if user_id is None else str(user_id)}
    if version >= 2:
        payload |= {"ip_address": None, "user_agent": None} | client
    return platform_events.new_event(
        reset_events.PASSWORD_RESET_REQUESTED, payload, source="test", schema_version=version
    )


class TestAnAdmittedRequest:
    def test_a_registered_address_gets_one_mail_whose_link_resets_the_password(
        self, client, committed_sessions, mail_on
    ):
        user = _user(committed_sessions)

        response = _request(client, user.email)

        assert response.status_code == 204
        (message,) = outbox()
        assert message.to == [user.email]
        assert "Password reset" in message.subject
        assert "/reset-password#token=" in (message.text or "")
        token = token_in(message)
        confirm = client.post(f"{_PUBLIC}/confirm", json={"token": token, "password": _NEW_PASSWORD})
        assert confirm.status_code == 204
        login = client.post(
            _LOGIN, data={"username": user.username, "password": _NEW_PASSWORD}, headers={"X-Client-Type": "web"}
        )
        assert login.status_code == 200

    def test_the_audit_row_names_the_account_and_the_requesters_client_without_the_address(
        self, client, committed_sessions, mail_on
    ):
        user = _user(committed_sessions)

        _request(client, user.email)

        (row,) = _requests_audited(committed_sessions)
        assert (row.outcome, row.target_type, row.target_id, row.target_owner_id) == (
            "success",
            "user",
            str(user.id),
            str(user.id),
        )
        assert row.user_agent == _AGENT
        assert row.ip_address
        assert row.details is None
        assert user.email not in repr(row.__dict__)

    def test_the_mail_is_in_the_users_language(self, client, committed_sessions, mail_on):
        user = _user(committed_sessions, preferred_language="pt-PT")

        _request(client, user.email)

        (message,) = outbox()
        assert 'lang="pt-PT"' in (message.html or "")

    def test_a_second_request_inside_the_cooldown_sends_nothing_more_and_adds_no_row(
        self, client, committed_sessions, mail_on
    ):
        user = _user(committed_sessions)

        first, second = _request(client, user.email), _request(client, user.email)

        assert (first.status_code, second.status_code) == (204, 204)
        assert len(outbox()) == 1
        assert len(_requests_audited(committed_sessions)) == 1
        assert len(_tokens(committed_sessions, user.id)) == 1

    def test_an_administrator_still_gets_the_mail_while_local_sign_in_is_off(self, client, committed_sessions, mail_on):
        with committed_sessions() as db:
            edit_server_settings(db, local_login_enabled=False)
            admin = make_admin(db)
            db.commit()

        _request(client, admin.email)

        assert [message.to for message in outbox()] == [[admin.email]]

    def test_a_cooldown_store_that_is_down_sends_nothing_and_adds_no_row(
        self, client, committed_sessions, mail_on, monkeypatch, app_log
    ):
        user = _user(committed_sessions)

        def down(*_args, **_kwargs):
            raise StateBackendUnavailableError("down")

        monkeypatch.setattr(platform_runtime.get_state(), "set_if_absent", down)

        assert _request(client, user.email).status_code == 204

        assert outbox() == []
        assert _requests_audited(committed_sessions) == []
        assert _tokens(committed_sessions, user.id) == []
        # An outage is a degraded path: logged as a warning, nothing as an error.
        assert max(r.levelno for r in app_log.records) == logging.WARNING


class TestARequestThatGetsNoMail:
    def test_an_unknown_address_gets_the_same_204_and_a_failure_row_without_a_target(
        self, client, committed_sessions, mail_on
    ):
        known = _user(committed_sessions)
        answered = _request(client, known.email)
        unknown = _request(client, "nobody@example.com")

        assert (unknown.status_code, unknown.content) == (answered.status_code, answered.content)
        assert len(outbox()) == 1
        rows = _requests_audited(committed_sessions)
        assert sorted((row.outcome, row.target_id is None) for row in rows) == [("failure", True), ("success", False)]

    @pytest.mark.parametrize(
        "account",
        [
            pytest.param({"active": False}, id="inactive"),
            pytest.param({"with_password": False}, id="no-local-password"),
        ],
    )
    def test_an_account_that_may_not_reset_is_answered_the_same_and_audited_as_denied(
        self, client, committed_sessions, mail_on, account
    ):
        user = _user(committed_sessions, **account)

        response = _request(client, user.email)

        assert response.status_code == 204
        assert outbox() == []
        (row,) = _requests_audited(committed_sessions)
        assert (row.outcome, row.target_id) == ("denied", str(user.id))
        assert _tokens(committed_sessions, user.id) == []

    def test_a_regular_account_gets_nothing_while_local_sign_in_is_off(self, client, committed_sessions, mail_on):
        with committed_sessions() as db:
            edit_server_settings(db, local_login_enabled=False)
            user = make_user(db)
            db.commit()

        assert _request(client, user.email).status_code == 204

        assert outbox() == []
        (row,) = _requests_audited(committed_sessions)
        assert row.outcome == "denied"

    def test_without_a_mail_server_the_request_is_503_and_nothing_is_recorded(self, client, committed_sessions):
        user = _user(committed_sessions)

        response = _request(client, user.email)

        assert response.status_code == 503
        assert _requests_audited(committed_sessions) == []

    @pytest.mark.parametrize(
        "body",
        [{"email": "not-an-address"}, {}, {"email": "a@example.com", "extra": 1}],
        ids=["malformed", "missing", "unknown-field"],
    )
    def test_a_malformed_request_is_422(self, client, mail_on, body):
        assert client.post(f"{_PUBLIC}/request", json=body).status_code == 422
        assert outbox() == []


class TestTheRequestEvent:
    def test_the_event_names_the_account_and_the_client_but_never_the_address(
        self, client, committed_sessions, mail_on
    ):
        seen: list[platform_events.Event] = []
        events().subscribe(reset_events.PASSWORD_RESET_REQUESTED, seen.append)
        user = _user(committed_sessions)

        _request(client, user.email)
        _request(client, "nobody@example.com")

        payloads = [event.payload for event in seen]
        assert [set(payload) for payload in payloads] == [{"user_id", "ip_address", "user_agent"}] * 2
        assert [payload["user_id"] for payload in payloads] == [str(user.id), None]
        assert payloads[0]["user_agent"] == _AGENT
        assert user.email not in repr(payloads)


class TestDelivery:
    def test_a_redelivered_event_resends_the_same_link_without_a_second_row(self, committed_sessions, mail_on):
        user = _user(committed_sessions)
        event = _event(user.id, ip_address="203.0.113.7", user_agent=_AGENT)

        reset_subscribers.send_password_reset_email_for_event(event)
        reset_subscribers.send_password_reset_email_for_event(event)

        first, second = outbox()
        assert token_in(first) == token_in(second)
        assert len(_tokens(committed_sessions, user.id)) == 1
        assert len(_requests_audited(committed_sessions)) == 1

    def test_a_retry_of_an_older_request_does_not_revoke_the_newer_link(self, committed_sessions, mail_on):
        user = _user(committed_sessions)
        older, newer = _event(user.id), _event(user.id)
        reset_subscribers.send_password_reset_email_for_event(older)
        state = platform_runtime.get_state()
        for key in list(state.iter_keys("endurain:auth:email_cooldown:")):
            state.delete(key)
        reset_subscribers.send_password_reset_email_for_event(newer)

        reset_subscribers.send_password_reset_email_for_event(older)

        first, second, retried = outbox()
        assert token_in(first) != token_in(second)
        assert token_in(retried) == token_in(first)
        usable = [token.used for token in _tokens(committed_sessions, user.id)]
        assert usable == [True, False]

    def test_a_user_deleted_since_the_request_gets_nothing_and_no_row(self, committed_sessions, mail_on):
        reset_subscribers.send_password_reset_email_for_event(_event(uuid.uuid4()))

        assert outbox() == []
        assert _requests_audited(committed_sessions) == []

    def test_a_queued_version_1_event_without_client_data_is_still_handled(self, committed_sessions, mail_on):
        user = _user(committed_sessions)

        reset_subscribers.send_password_reset_email_for_event(_event(user.id, version=1))

        assert len(outbox()) == 1
        (row,) = _requests_audited(committed_sessions)
        assert (row.ip_address, row.user_agent) == (None, None)

    def test_a_transient_mail_failure_fails_the_durable_run_so_it_is_retried_but_not_the_bus_one(
        self, committed_sessions, mail_on, monkeypatch
    ):
        user = _user(committed_sessions)

        def refuse(_message):
            raise MailError("try again", status=421)

        monkeypatch.setattr(platform_runtime.get_active_platform().mail, "send", refuse)

        with pytest.raises(MailError):
            reset_subscribers.send_password_reset_email_for_event(_event(user.id))
        reset_subscribers.on_password_reset_requested(_event(user.id))

    def test_a_permanent_mail_refusal_is_dropped_without_failing_the_run(
        self, committed_sessions, mail_on, monkeypatch
    ):
        user = _user(committed_sessions)

        def refuse(_message):
            raise MailError("no such mailbox", status=550)

        monkeypatch.setattr(platform_runtime.get_active_platform().mail, "send", refuse)

        reset_subscribers.send_password_reset_email_for_event(_event(user.id))

        assert outbox() == []

    def test_the_durable_handler_is_registered_for_the_request_event(self):
        from jasil.jobs.registry import JobHandlerRegistry

        registry = JobHandlerRegistry()
        reset_subscriber_registry.register_durable_handlers(registry)

        assert registry.subscribers_for(reset_events.PASSWORD_RESET_REQUESTED) == (
            reset_subscribers.PASSWORD_RESET_EMAIL_SUBSCRIBER_ID,
        )
        (net,) = reset_subscriber_registry.DURABLE_SUBSCRIBER_NETS
        assert net.subscriber_id == reset_subscribers.PASSWORD_RESET_EMAIL_SUBSCRIBER_ID
        assert net.backfill is None and net.exempt_reason
