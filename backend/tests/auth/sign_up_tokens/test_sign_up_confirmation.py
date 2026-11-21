"""Confirming a sign-up or an email change: which accounts a link serves, what it replaces and what it refuses."""

import jasil.events as platform_events
import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa

import core.config as core_config
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.credentials.models as credentials_models
import modules.auth.password_reset_tokens.models as reset_models
import modules.auth.sessions.models as sessions_models
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.auth.sign_up_tokens.integration_service as sign_up_integration
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.scheduled_jobs as sign_up_scheduled_jobs
import modules.auth.sign_up_tokens.subscriber_registry as sign_up_subscriber_registry
import modules.auth.sign_up_tokens.subscribers as sign_up_subscribers
import modules.users.users.models as users_models
from tests._factories.mail import configure_mail, events, outbox
from tests._factories.server_settings import edit_mail_settings, edit_server_settings
from tests._factories.tokens import make_email_change, make_reset_token, make_sign_up_token
from tests._factories.users import PASSWORD, make_user

_PUBLIC = f"{core_config.ROOT_PATH}/public"
_LOGIN = f"{core_config.ROOT_PATH}/auth/login"
_CHOSEN = "Chosen-Password-7788!"
_INVALID_INPUT = "urn:endurain:error:invalid-input"


def _policy(committed_sessions, *, enabled=True, verification=True, approval=False) -> None:
    with committed_sessions() as db:
        edit_server_settings(
            db,
            signup_enabled=enabled,
            signup_require_email_verification=verification,
            signup_require_admin_approval=approval,
        )
        db.commit()


def _confirm(client, token: str, password: str = _CHOSEN):
    return client.post(f"{_PUBLIC}/sign-up/confirm", json={"token": token, "password": password})


def _sign_in(client, username: str, password: str):
    return client.post(_LOGIN, data={"username": username, "password": password}, headers={"X-Client-Type": "web"})


def _row(committed_sessions, user_id) -> users_models.Users:
    with committed_sessions() as db:
        return db.scalars(sa.select(users_models.Users).where(users_models.Users.id == user_id)).one()


def _hash(committed_sessions, user_id) -> str | None:
    with committed_sessions() as db:
        return db.scalar(
            sa.select(credentials_models.LocalCredential.password_hash).where(
                credentials_models.LocalCredential.user_id == user_id
            )
        )


def _with_token(committed_sessions, **account):
    with committed_sessions() as db:
        user = make_user(db, **account)
        token = make_sign_up_token(db, user)
        db.commit()
    return user, token


class TestWhichAccountsALinkServes:
    def test_a_sign_up_awaiting_verification_is_activated_and_chooses_its_password(self, client, committed_sessions):
        _policy(committed_sessions)
        user, token = _with_token(
            committed_sessions, active=False, email_verified=False, with_password=False, deactivated_at=None
        )

        response = _confirm(client, token)

        assert (response.status_code, response.json()) == (200, {"next_step": "sign_in"})
        assert (_row(committed_sessions, user.id).active, _row(committed_sessions, user.id).email_verified) == (
            True,
            True,
        )
        assert _sign_in(client, user.username, _CHOSEN).status_code == 200

    def test_an_account_an_administrator_activated_before_confirming_chooses_its_password_even_with_sign_up_off(
        self, client, committed_sessions
    ):
        _policy(committed_sessions, enabled=False)
        user, token = _with_token(committed_sessions, with_password=False, email_verified=False)

        response = _confirm(client, token)

        assert response.status_code == 200
        assert _sign_in(client, user.username, _CHOSEN).status_code == 200

    def test_an_account_that_has_a_password_takes_none_from_a_link(self, client, committed_sessions):
        _policy(committed_sessions)
        user, token = _with_token(committed_sessions)
        before = _hash(committed_sessions, user.id)

        response = _confirm(client, token)

        assert (response.status_code, response.json()["type"]) == (400, _INVALID_INPUT)
        assert _hash(committed_sessions, user.id) == before
        assert _sign_in(client, user.username, PASSWORD).status_code == 200

    def test_a_deactivated_account_is_refused_by_a_sign_up_link_and_left_alone(self, client, committed_sessions):
        _policy(committed_sessions)
        user, token = _with_token(committed_sessions, active=False, email_verified=False, with_password=False)

        response = _confirm(client, token)

        assert (response.status_code, response.json()["type"]) == (400, _INVALID_INPUT)
        row = _row(committed_sessions, user.id)
        assert (row.active, row.email_verified, _hash(committed_sessions, user.id)) == (False, False, None)

    def test_an_email_change_link_switches_the_address_and_keeps_a_deactivated_account_inactive(
        self, client, committed_sessions
    ):
        with committed_sessions() as db:
            user = make_user(db, active=False, email_verified=False)
            change = make_email_change(db, user, "moved@example.com")
            db.commit()

        response = client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token})

        assert response.status_code == 204
        row = _row(committed_sessions, user.id)
        assert (row.email, row.active, row.email_verified) == ("moved@example.com", False, True)

    def test_a_sign_up_confirmed_while_verification_is_off_is_the_email_verification_disabled_problem(
        self, client, committed_sessions
    ):
        _policy(committed_sessions, verification=False)
        user, token = _with_token(
            committed_sessions, active=False, email_verified=False, with_password=False, deactivated_at=None
        )

        response = _confirm(client, token)

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:email-verification-disabled"
        assert _row(committed_sessions, user.id).active is False

    def test_a_sign_up_that_needs_approval_goes_on_to_it_and_stays_inactive(self, client, committed_sessions):
        _policy(committed_sessions, approval=True)
        user, token = _with_token(
            committed_sessions, active=False, email_verified=False, with_password=False, deactivated_at=None
        )

        response = _confirm(client, token)

        assert response.json() == {"next_step": "await_approval"}
        row = _row(committed_sessions, user.id)
        assert (row.active, row.email_verified) == (False, True)


class TestWhatAConfirmationReplaces:
    def test_it_replaces_an_existing_hash_voids_reset_links_and_ends_sessions(
        self, client, committed_sessions, sign_in
    ):
        _policy(committed_sessions)
        with committed_sessions() as db:
            user = make_user(db, active=False, email_verified=False, with_password=False, deactivated_at=None)
            token = make_sign_up_token(db, user)
            reset = make_reset_token(db, user)
            db.commit()
        # A hash staged at sign-up by whoever knew the address does not survive the owner's choice.
        with committed_sessions() as db:
            credentials_integration.set_local_password_hash(
                user.id, "staged-by-someone-else", db, change_required=False
            )
            db.commit()
        holder = sign_in(user)

        assert _confirm(client, token).status_code == 200

        assert _hash(committed_sessions, user.id) != "staged-by-someone-else"
        assert _sign_in(client, user.username, _CHOSEN).status_code == 200
        with committed_sessions() as db:
            assert db.get(sessions_models.UsersSessions, holder.session_id) is None
            assert set(db.scalars(sa.select(reset_models.PasswordResetToken.used))) == {True}
        assert (
            client.post(f"{_PUBLIC}/password-reset/confirm", json={"token": reset, "password": _CHOSEN}).status_code
            == 400
        )

    def test_a_password_the_policy_refuses_leaves_the_link_usable(self, client, committed_sessions):
        _policy(committed_sessions)
        user, token = _with_token(
            committed_sessions, active=False, email_verified=False, with_password=False, deactivated_at=None
        )

        refused = _confirm(client, token, "short")

        assert refused.status_code == 422
        assert refused.json()["type"] == "urn:endurain:error:password-too-short"
        assert _row(committed_sessions, user.id).active is False
        assert _confirm(client, token).status_code == 200

    def test_a_confirmed_change_voids_the_accounts_reset_links(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "moved@example.com")
            reset = make_reset_token(db, user)
            db.commit()

        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token}).status_code == 204

        assert (
            client.post(f"{_PUBLIC}/password-reset/confirm", json={"token": reset, "password": _CHOSEN}).status_code
            == 400
        )

    @pytest.mark.parametrize(
        ("route", "body"),
        [
            ("sign-up/confirm", {"password": _CHOSEN}),
            ("sign-up/confirm", {"token": "t"}),
            ("sign-up/confirm", {"token": "t", "password": _CHOSEN, "extra": 1}),
            ("email-change/confirm", {}),
            ("email-change/confirm", {"token": "t", "password": _CHOSEN}),
        ],
        ids=["no-token", "no-password", "extra-field", "change-no-token", "change-with-password"],
    )
    def test_a_malformed_confirmation_is_422(self, client, route, body):
        assert client.post(f"{_PUBLIC}/{route}", json=body).status_code == 422


class TestRevokingPendingTokens:
    def test_it_voids_only_that_users_unused_tokens(self, committed_sessions):
        with committed_sessions() as db:
            mine, other = make_user(db), make_user(db)
            make_sign_up_token(db, mine)
            make_sign_up_token(db, other)
            sign_up_integration.revoke_pending_tokens(mine.id, db)
            db.commit()

        with committed_sessions() as db:
            used = dict(
                db.execute(sa.select(sign_up_models.SignUpToken.user_id, sign_up_models.SignUpToken.used)).all()
            )
        assert used == {mine.id: True, other.id: False}


class TestWithNothingToDo:
    def test_the_jobs_run_cleanly_on_an_empty_database(self, committed_sessions):
        sign_up_scheduled_jobs.delete_expired_tokens_from_db()
        sign_up_scheduled_jobs.delete_unverified_sign_ups_from_db()


class TestDeliveryGuards:
    @pytest.fixture(autouse=True)
    def _mail_on(self, committed_sessions):
        configure_mail(committed_sessions)
        sign_up_subscriber_registry.register_bus_subscribers(events())

    def _deliver(self, handler, event_type, user):
        handler(platform_events.new_event(event_type, {"user_id": str(user.id)}, source="test"))

    def test_an_email_change_event_without_a_pending_change_mails_nobody(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()

        self._deliver(
            sign_up_subscribers.send_email_change_verification_email_for_event,
            sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
            user,
        )
        self._deliver(
            sign_up_subscribers.send_email_change_requested_email_for_event,
            sign_up_events.EMAIL_CHANGE_REQUESTED,
            user,
        )

        assert outbox() == []

    def test_an_address_taken_after_the_request_gets_no_confirmation_link(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            sign_up_integration.request_email_change(user.id, "contested@example.com", user.email, db)
            make_user(db, email="contested@example.com")
            db.commit()
        before = len(outbox())

        self._deliver(
            sign_up_subscribers.send_email_change_verification_email_for_event,
            sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
            user,
        )

        assert len(outbox()) == before
        assert not [m for m in outbox() if m.to == ["contested@example.com"]]

    def test_a_resend_after_mail_was_switched_off_does_nothing(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            sign_up_integration.request_email_change(user.id, "new@example.com", user.email, db)
            edit_mail_settings(db, host=None)
            db.commit()
        before = len(outbox())

        with committed_sessions() as db:
            sign_up_integration.request_email_change_resend(user.id, platform_runtime.get_state(), db)
            db.commit()

        assert len(outbox()) == before
