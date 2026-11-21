"""Signing up and asking for the verification mail again, on the real application with its mail subscribers."""

import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa
from jasil.providers import StateBackendUnavailableError

import core.config as core_config
import modules.auth.sign_up_tokens.subscriber_registry as sign_up_subscriber_registry
import modules.users.users.models as users_models
from tests._factories.breach import fake_range_api
from tests._factories.mail import configure_mail, events, outbox, token_in
from tests._factories.server_settings import edit_mail_settings, edit_server_settings
from tests._factories.tokens import make_email_change
from tests._factories.users import make_admin, make_sign_up, make_user

_PUBLIC = f"{core_config.ROOT_PATH}/public"
_LOGIN = f"{core_config.ROOT_PATH}/auth/login"
_PASSWORD = "A long sign-up passphrase 2026!"
_INVALID_INPUT = "urn:endurain:error:invalid-input"
_SIGN_UP = {"name": "Ana Silva", "username": "ana", "email": "ana@example.com"}


@pytest.fixture
def mail_on(committed_sessions):
    """Mail is configured and the sign-up mail subscribers listen on the bus."""
    configure_mail(committed_sessions)
    sign_up_subscriber_registry.register_bus_subscribers(events())


def _policy(committed_sessions, *, enabled=True, verification=True, approval=False) -> None:
    with committed_sessions() as db:
        edit_server_settings(
            db,
            signup_enabled=enabled,
            signup_require_email_verification=verification,
            signup_require_admin_approval=approval,
        )
        db.commit()


def _sign_up(client, **fields):
    return client.post(f"{_PUBLIC}/sign-up/request", json={**_SIGN_UP, **fields})


def _resend(client, email: str):
    return client.post(f"{_PUBLIC}/sign-up/resend", json={"email": email})


def _users_named(committed_sessions, username: str) -> list[users_models.Users]:
    with committed_sessions() as db:
        return list(db.scalars(sa.select(users_models.Users).where(users_models.Users.username == username)))


def _sign_in(client, username: str, password: str):
    return client.post(_LOGIN, data={"username": username, "password": password}, headers={"X-Client-Type": "web"})


def _mailed_to(address: str):
    return [message for message in outbox() if message.to == [address]]


class TestAnEmailVerifiedSignUp:
    def test_the_account_waits_for_its_mailed_link_and_the_password_is_chosen_there(
        self, client, committed_sessions, mail_on
    ):
        _policy(committed_sessions)

        response = _sign_up(client)

        assert (response.status_code, response.json()) == (200, {"next_step": "check_email"})
        (user,) = _users_named(committed_sessions, "ana")
        assert (user.active, user.email_verified) == (False, False)
        (message,) = _mailed_to("ana@example.com")
        assert "/signup/confirm#token=" in (message.text or "")
        confirm = client.post(f"{_PUBLIC}/sign-up/confirm", json={"token": token_in(message), "password": _PASSWORD})
        assert (confirm.status_code, confirm.json()) == (200, {"next_step": "sign_in"})
        assert _sign_in(client, "ana", _PASSWORD).status_code == 200

    def test_a_password_in_the_request_is_refused_and_no_account_is_made(self, client, committed_sessions, mail_on):
        _policy(committed_sessions)

        response = _sign_up(client, password=_PASSWORD)

        assert (response.status_code, response.json()["type"]) == (400, _INVALID_INPUT)
        assert _users_named(committed_sessions, "ana") == []
        assert outbox() == []

    def test_without_a_mail_server_nothing_is_created(self, client, committed_sessions):
        _policy(committed_sessions)

        response = _sign_up(client)

        assert response.status_code == 503
        assert _users_named(committed_sessions, "ana") == []

    def test_an_approval_after_verification_asks_every_administrator_once_the_address_is_verified(
        self, client, committed_sessions, mail_on
    ):
        _policy(committed_sessions, approval=True)
        with committed_sessions() as db:
            first, second = make_admin(db), make_admin(db)
            make_user(db)
            db.commit()
        _sign_up(client)
        (link,) = _mailed_to("ana@example.com")
        assert not [m for m in outbox() if m.to in ([first.email], [second.email])]

        confirm = client.post(f"{_PUBLIC}/sign-up/confirm", json={"token": token_in(link), "password": _PASSWORD})

        assert confirm.json() == {"next_step": "await_approval"}
        assert len(_mailed_to(first.email)) == len(_mailed_to(second.email)) == 1
        assert _mailed_to(first.email)[0].subject == "Endurain - New user sign-up pending approval"
        assert "ana" in (_mailed_to(first.email)[0].text or "")
        (user,) = _users_named(committed_sessions, "ana")
        assert (user.active, user.email_verified) == (False, True)


class TestASignUpWithoutVerification:
    def test_the_password_is_set_at_sign_up_and_the_account_signs_in(self, client, committed_sessions, mail_on):
        _policy(committed_sessions, verification=False)

        response = _sign_up(client, password=_PASSWORD)

        assert (response.status_code, response.json()) == (200, {"next_step": "sign_in"})
        assert outbox() == []
        assert _sign_in(client, "ana", _PASSWORD).status_code == 200

    def test_a_missing_password_is_the_password_required_problem(self, client, committed_sessions):
        _policy(committed_sessions, verification=False)

        response = _sign_up(client)

        assert response.status_code == 400
        assert response.json()["type"] == "urn:endurain:error:password-required"
        assert _users_named(committed_sessions, "ana") == []

    def test_a_password_the_policy_refuses_creates_nothing(self, client, committed_sessions):
        _policy(committed_sessions, verification=False)

        response = _sign_up(client, password="short")

        assert response.status_code == 422
        assert response.json()["type"] == "urn:endurain:error:password-too-short"
        assert _users_named(committed_sessions, "ana") == []

    def test_a_breached_password_creates_nothing(self, client, committed_sessions, monkeypatch):
        fake_range_api(monkeypatch).breach(_PASSWORD)
        _policy(committed_sessions, verification=False)
        with committed_sessions() as db:
            edit_server_settings(db, password_breach_check_enabled=True)
            db.commit()

        response = _sign_up(client, password=_PASSWORD)

        assert response.status_code == 422
        assert response.json()["type"] == "urn:endurain:error:password-breached"
        assert _users_named(committed_sessions, "ana") == []

    def test_an_account_awaiting_approval_asks_the_administrators_at_once(self, client, committed_sessions, mail_on):
        _policy(committed_sessions, verification=False, approval=True)
        with committed_sessions() as db:
            admin = make_admin(db)
            db.commit()

        response = _sign_up(client, password=_PASSWORD)

        assert response.json() == {"next_step": "await_approval"}
        (user,) = _users_named(committed_sessions, "ana")
        assert (user.active, user.pending_admin_approval) == (False, True)
        assert len(_mailed_to(admin.email)) == 1
        assert _sign_in(client, "ana", _PASSWORD).status_code == 401

    def test_without_a_mail_server_the_approval_waits_unannounced_and_the_answer_is_the_same(
        self, client, committed_sessions
    ):
        _policy(committed_sessions, verification=False, approval=True)
        with committed_sessions() as db:
            make_admin(db)
            db.commit()

        assert _sign_up(client, password=_PASSWORD).json() == {"next_step": "await_approval"}
        assert outbox() == []


class TestSignUpRefusals:
    def test_a_disabled_registration_is_refused_before_anything_else(self, client, committed_sessions, mail_on):
        _policy(committed_sessions, enabled=False)

        response = _sign_up(client, password=_PASSWORD)

        assert response.status_code == 403
        assert _users_named(committed_sessions, "ana") == []

    def test_a_taken_username_is_a_conflict_that_tells_nobody_and_creates_nothing(
        self, client, committed_sessions, mail_on
    ):
        _policy(committed_sessions)
        with committed_sessions() as db:
            owner = make_user(db, username="ana")
            holder = make_user(db, email="ana@example.com")
            db.commit()

        response = _sign_up(client)

        assert response.status_code == 409
        assert len(_users_named(committed_sessions, "ana")) == 1
        assert outbox() == []
        assert owner.username == "ana" and holder.email == "ana@example.com"

    @pytest.mark.parametrize(
        "extra",
        [{"access_type": "admin"}, {"active": True}, {"city": "Faro"}, {"unknown": 1}],
        ids=["access-type", "active", "profile-field", "unknown"],
    )
    def test_a_field_beyond_the_sign_up_details_is_422(self, client, committed_sessions, mail_on, extra):
        _policy(committed_sessions)

        assert _sign_up(client, **extra).status_code == 422
        assert _users_named(committed_sessions, "ana") == []

    @pytest.mark.parametrize("missing", ["name", "username", "email"])
    def test_every_detail_is_required(self, client, committed_sessions, missing):
        _policy(committed_sessions)
        body = {key: value for key, value in _SIGN_UP.items() if key != missing}

        assert client.post(f"{_PUBLIC}/sign-up/request", json=body).status_code == 422


class TestASignUpWithARegisteredAddress:
    def _owner(self, committed_sessions, **fields):
        with committed_sessions() as db:
            owner = make_user(db, email="ana@example.com", **fields)
            db.commit()
        return owner

    def test_it_answers_like_a_new_account_creates_nothing_and_tells_the_owner(
        self, client, committed_sessions, mail_on
    ):
        _policy(committed_sessions)
        owner = self._owner(committed_sessions)
        fresh = _sign_up(client, username="fresh", email="fresh@example.com")
        taken = _sign_up(client)

        assert (taken.status_code, taken.json()) == (fresh.status_code, fresh.json())
        assert _users_named(committed_sessions, "ana") == []
        (notice,) = _mailed_to(owner.email)
        assert notice.subject == "Endurain - Sign-up attempt with your email"
        assert len(_mailed_to("fresh@example.com")) == 1

    def test_the_owner_is_told_once_per_cooldown_and_each_owner_has_their_own(
        self, client, committed_sessions, mail_on
    ):
        _policy(committed_sessions)
        first = self._owner(committed_sessions)
        with committed_sessions() as db:
            second = make_user(db, email="bo@example.com")
            db.commit()

        _sign_up(client)
        _sign_up(client, username="ana2")
        _sign_up(client, username="bo", email="bo@example.com")

        assert len(_mailed_to(first.email)) == 1
        assert len(_mailed_to(second.email)) == 1

    def test_an_unreachable_cooldown_store_skips_the_notice_without_changing_the_answer(
        self, client, committed_sessions, mail_on, monkeypatch
    ):
        _policy(committed_sessions)
        self._owner(committed_sessions)

        def down(*_args, **_kwargs):
            raise StateBackendUnavailableError("down")

        monkeypatch.setattr(platform_runtime.get_state(), "set_if_absent", down)

        response = _sign_up(client)

        assert (response.status_code, response.json()) == (200, {"next_step": "check_email"})
        assert outbox() == []

    def test_without_a_mail_server_there_is_no_notice_and_the_answer_is_the_same(self, client, committed_sessions):
        _policy(committed_sessions)
        self._owner(committed_sessions)

        response = _sign_up(client)

        assert (response.status_code, response.json()) == (200, {"next_step": "check_email"})
        assert outbox() == []

    def test_an_address_reserved_for_a_revert_window_is_answered_like_a_held_one(
        self, client, committed_sessions, mail_on
    ):
        _policy(committed_sessions)
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "moved@example.com")
            db.commit()
        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token}).status_code == 204

        response = _sign_up(client, email=user.email)

        assert (response.status_code, response.json()) == (200, {"next_step": "check_email"})
        assert _users_named(committed_sessions, "ana") == []
        assert any(to != "moved@example.com" for message in outbox() for to in message.to)
        assert len(_mailed_to(user.email)) >= 1


class TestResendingTheVerificationMail:
    def _pending(self, committed_sessions, **fields):
        with committed_sessions() as db:
            user = make_sign_up(db, with_password=False, **fields)
            db.commit()
        return user

    def test_an_account_awaiting_verification_gets_a_fresh_link_that_confirms_it(
        self, client, committed_sessions, mail_on
    ):
        _policy(committed_sessions)
        user = self._pending(committed_sessions)

        response = _resend(client, user.email)

        assert (response.status_code, response.json()) == (200, {"next_step": "check_email"})
        (message,) = _mailed_to(user.email)
        confirm = client.post(f"{_PUBLIC}/sign-up/confirm", json={"token": token_in(message), "password": _PASSWORD})
        assert confirm.status_code == 200
        assert _sign_in(client, user.username, _PASSWORD).status_code == 200

    def test_a_second_request_inside_the_cooldown_sends_nothing_more(self, client, committed_sessions, mail_on):
        _policy(committed_sessions)
        user = self._pending(committed_sessions)

        first, second = _resend(client, user.email), _resend(client, user.email)

        assert first.json() == second.json()
        assert len(_mailed_to(user.email)) == 1

    def test_every_outcome_gets_the_same_answer_and_only_a_pending_account_is_mailed(
        self, client, committed_sessions, mail_on
    ):
        _policy(committed_sessions)
        with committed_sessions() as db:
            pending = make_sign_up(db, with_password=False)
            active = make_user(db)
            verified = make_sign_up(db, email_verified=True, with_password=False)
            deactivated = make_user(db, active=False, email_verified=False, with_password=False)
            db.commit()

        answers = [
            _resend(client, address)
            for address in (pending.email, active.email, verified.email, deactivated.email, "nobody@example.com")
        ]

        assert {(answer.status_code, answer.content) for answer in answers} == {(200, answers[0].content)}
        assert [message.to for message in outbox()] == [[pending.email]]

    def test_nothing_is_sent_without_verification_or_without_a_mail_server(self, client, committed_sessions):
        user = self._pending(committed_sessions)
        _policy(committed_sessions, verification=False)
        configure_mail(committed_sessions)
        sign_up_subscriber_registry.register_bus_subscribers(events())
        assert _resend(client, user.email).json() == {"next_step": "check_email"}
        _policy(committed_sessions, verification=True)
        with committed_sessions() as db:
            edit_mail_settings(db, host=None)
            db.commit()

        assert _resend(client, user.email).json() == {"next_step": "check_email"}
        assert outbox() == []

    def test_an_unreachable_cooldown_store_skips_the_send(self, client, committed_sessions, mail_on, monkeypatch):
        _policy(committed_sessions)
        user = self._pending(committed_sessions)

        def down(*_args, **_kwargs):
            raise StateBackendUnavailableError("down")

        monkeypatch.setattr(platform_runtime.get_state(), "set_if_absent", down)

        assert _resend(client, user.email).status_code == 200
        assert outbox() == []

    def test_with_sign_up_off_the_resend_is_refused_whatever_the_address(self, client, committed_sessions, mail_on):
        _policy(committed_sessions, enabled=False)
        user = self._pending(committed_sessions)

        assert _resend(client, user.email).status_code == 403
        assert _resend(client, "nobody@example.com").status_code == 403

    def test_a_malformed_address_is_422(self, client):
        assert _resend(client, "not-an-address").status_code == 422
        assert client.post(f"{_PUBLIC}/sign-up/resend", json={}).status_code == 422

    def test_a_resend_keeps_the_account_until_the_mailed_link_replaces_the_token(
        self, client, committed_sessions, mail_on
    ):
        _policy(committed_sessions)
        user = self._pending(committed_sessions)

        _resend(client, user.email)

        (kept,) = _users_named(committed_sessions, user.username)
        assert (kept.active, kept.email_verified) == (False, False)
