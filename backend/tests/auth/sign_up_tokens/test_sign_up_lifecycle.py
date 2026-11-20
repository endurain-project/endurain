"""Sign-up and email-change tokens work once and expire; an email change can be reported as not made by the owner."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi.testclient import TestClient

import core.config as core_config
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.models as api_keys_models
import modules.auth.password_reset_tokens.models as reset_models
import modules.auth.sessions.models as sessions_models
import modules.auth.sign_up_tokens.audit_actions as sign_up_audit_actions
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.server_settings.models as server_settings_models
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.models as users_models
from tests._factories.api_keys import make_api_key
from tests._factories.tokens import audit_rows, make_email_change, make_reset_token, make_sign_up_token
from tests._factories.users import make_user

_PUBLIC = f"{core_config.ROOT_PATH}/public"
_LOGIN = f"{core_config.ROOT_PATH}/auth/login"
_PROFILE = f"{core_config.ROOT_PATH}/profile"
_CHOSEN_PASSWORD = "Chosen-Password-7788!"
_INVALID_INPUT = "urn:endurain:error:invalid-input"


def _configure_sign_up(committed_sessions, *, enabled=True, verification=True, approval=False) -> None:
    with committed_sessions() as db:
        db.execute(
            sa.update(server_settings_models.ServerSettings).values(
                signup_enabled=enabled,
                signup_require_email_verification=verification,
                signup_require_admin_approval=approval,
            )
        )
        db.commit()


def _pending_sign_up(committed_sessions, **token_options):
    """A sign-up awaiting its confirmation: an inactive, unverified account with no password and its token."""
    with committed_sessions() as db:
        user = make_user(db, active=False, email_verified=False, with_password=False, deactivated_at=None)
        token = make_sign_up_token(db, user, **token_options)
        db.commit()
    return user, token


def _user_row(committed_sessions, user_id) -> users_models.Users:
    with committed_sessions() as db:
        return db.scalars(sa.select(users_models.Users).where(users_models.Users.id == user_id)).one()


def _confirm_sign_up(client: TestClient, token: str, password: str = _CHOSEN_PASSWORD):
    return client.post(f"{_PUBLIC}/sign-up/confirm", json={"token": token, "password": password})


def _sign_in_with(client: TestClient, username: str, password: str):
    return client.post(_LOGIN, data={"username": username, "password": password}, headers={"X-Client-Type": "web"})


def _token_used(committed_sessions, user_id) -> list[bool]:
    with committed_sessions() as db:
        return list(
            db.scalars(
                sa.select(sign_up_models.SignUpToken.used)
                .where(sign_up_models.SignUpToken.user_id == user_id)
                .order_by(sign_up_models.SignUpToken.created_at)
            )
        )


class TestSignUpConfirmation:
    def test_a_token_activates_the_account_with_the_chosen_password_once(self, client, committed_sessions):
        _configure_sign_up(committed_sessions)
        user, token = _pending_sign_up(committed_sessions)

        first = _confirm_sign_up(client, token)
        second = _confirm_sign_up(client, token, "Second-Password-1122!")

        assert first.status_code == 200
        assert first.json()["next_step"] == "sign_in"
        assert second.status_code == 400
        assert second.json()["type"] == _INVALID_INPUT
        row = _user_row(committed_sessions, user.id)
        assert (row.active, row.email_verified) == (True, True)
        assert _sign_in_with(client, user.username, _CHOSEN_PASSWORD).status_code == 200
        assert _sign_in_with(client, user.username, "Second-Password-1122!").status_code == 401
        rows = audit_rows(committed_sessions, sign_up_audit_actions.SIGN_UP_CONFIRM)
        assert [(row.outcome, row.target_id) for row in rows] == [("success", str(user.id)), ("failure", None)]
        assert rows[0].details == {"password_set": True, "reason": None}

    def test_an_expired_token_is_refused_and_the_account_stays_pending(self, client, committed_sessions):
        _configure_sign_up(committed_sessions)
        user, token = _pending_sign_up(committed_sessions, expires_at=datetime.now(UTC) - timedelta(seconds=1))

        response = _confirm_sign_up(client, token)

        assert response.status_code == 400
        assert response.json()["type"] == _INVALID_INPUT
        row = _user_row(committed_sessions, user.id)
        assert (row.active, row.email_verified) == (False, False)
        assert _sign_in_with(client, user.username, _CHOSEN_PASSWORD).status_code == 401
        rows = audit_rows(committed_sessions, sign_up_audit_actions.SIGN_UP_CONFIRM)
        assert [row.outcome for row in rows] == ["failure"]

    def test_a_newer_token_replaces_the_older_one(self, client, committed_sessions):
        _configure_sign_up(committed_sessions)
        user, old = _pending_sign_up(committed_sessions)
        with committed_sessions() as db:
            new = make_sign_up_token(db, user)
            db.commit()

        assert _confirm_sign_up(client, old).status_code == 400
        assert _confirm_sign_up(client, new).status_code == 200
        assert _token_used(committed_sessions, user.id) == [True, True]

    def test_confirming_while_sign_up_is_off_is_refused_and_the_link_survives(self, client, committed_sessions):
        _configure_sign_up(committed_sessions, enabled=False)
        user, token = _pending_sign_up(committed_sessions)

        response = _confirm_sign_up(client, token)

        assert response.status_code == 403
        assert _token_used(committed_sessions, user.id) == [False]
        assert _user_row(committed_sessions, user.id).active is False
        rows = audit_rows(committed_sessions, sign_up_audit_actions.SIGN_UP_CONFIRM)
        assert [(row.outcome, row.target_id, row.details["reason"]) for row in rows] == [
            ("failure", str(user.id), "sign_up_disabled")
        ]
        _configure_sign_up(committed_sessions)
        assert _confirm_sign_up(client, token).status_code == 200

    def test_a_sign_up_that_needs_approval_verifies_the_email_and_stays_inactive(self, client, committed_sessions):
        _configure_sign_up(committed_sessions, approval=True)
        user, token = _pending_sign_up(committed_sessions)

        response = _confirm_sign_up(client, token)

        assert response.status_code == 200
        assert response.json()["next_step"] == "await_approval"
        row = _user_row(committed_sessions, user.id)
        assert (row.active, row.email_verified) == (False, True)
        assert _sign_in_with(client, user.username, _CHOSEN_PASSWORD).status_code == 401

    def test_two_simultaneous_confirmations_of_one_token_succeed_once(self, app, committed_sessions):
        _configure_sign_up(committed_sessions)
        user, token = _pending_sign_up(committed_sessions)
        barrier = threading.Barrier(2)
        passwords = (_CHOSEN_PASSWORD, "Second-Password-1122!")

        def confirm(password: str):
            client = TestClient(app)
            barrier.wait(timeout=10)
            return _confirm_sign_up(client, token, password)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [future.result(timeout=60) for future in [pool.submit(confirm, p) for p in passwords]]

        assert sorted(response.status_code for response in responses) == [200, 400]
        winner = passwords[[response.status_code for response in responses].index(200)]
        assert _sign_in_with(TestClient(app), user.username, winner).status_code == 200
        rows = audit_rows(committed_sessions, sign_up_audit_actions.SIGN_UP_CONFIRM)
        assert sorted(row.outcome for row in rows) == ["failure", "success"]

    def test_an_email_change_token_is_refused_here_and_keeps_working_for_its_own_route(
        self, client, committed_sessions
    ):
        _configure_sign_up(committed_sessions)
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "new-address@example.com")
            db.commit()

        assert _confirm_sign_up(client, change.token).status_code == 400
        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token}).status_code == 204


class TestEmailChangeConfirmation:
    def test_a_token_switches_the_address_once(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "new-address@example.com")
            db.commit()

        first = client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token})
        second = client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token})

        assert first.status_code == 204
        assert second.status_code == 400
        assert second.json()["type"] == _INVALID_INPUT
        row = _user_row(committed_sessions, user.id)
        assert (row.email, row.email_verified) == ("new-address@example.com", True)
        changed = audit_rows(committed_sessions, users_audit_actions.USER_EMAIL_CHANGE)
        assert [(row.outcome, row.target_id) for row in changed] == [("success", str(user.id))]
        refused = audit_rows(committed_sessions, sign_up_audit_actions.SIGN_UP_CONFIRM)
        assert [(row.outcome, row.target_id) for row in refused] == [("failure", None)]

    def test_an_expired_token_is_refused_and_the_address_is_kept(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "new-address@example.com", expires_at=datetime.now(UTC) - timedelta(1))
            db.commit()

        response = client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token})

        assert response.status_code == 400
        assert _user_row(committed_sessions, user.id).email == user.email

    def test_a_sign_up_token_is_refused_here(self, client, committed_sessions):
        _, token = _pending_sign_up(committed_sessions)

        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": token}).status_code == 400

    def test_a_security_change_after_the_request_voids_the_token(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "new-address@example.com")
            reset = make_reset_token(db, user)
            db.commit()
        assert (
            client.post(
                f"{_PUBLIC}/password-reset/confirm", json={"token": reset, "password": _CHOSEN_PASSWORD}
            ).status_code
            == 204
        )

        response = client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token})

        assert response.status_code == 400
        assert _user_row(committed_sessions, user.id).email == user.email
        rows = audit_rows(committed_sessions, sign_up_audit_actions.SIGN_UP_CONFIRM)
        assert [(row.outcome, row.details["reason"]) for row in rows] == [("failure", "security_changed")]

    def test_an_address_taken_meanwhile_is_a_conflict_and_the_token_stays_unused(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "contested@example.com")
            make_user(db, email="contested@example.com")
            db.commit()

        response = client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token})

        assert response.status_code == 409
        assert _user_row(committed_sessions, user.id).email == user.email
        assert _token_used(committed_sessions, user.id) == [False]


class TestEmailChangeRevert:
    def _confirmed_change(self, client, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "new-address@example.com")
            key, _ = make_api_key(db, user, scopes=[api_keys_constants.ApiKeyScope.ACCOUNT])
            reset = make_reset_token(db, user)
            db.commit()
        holder = sign_in(user)
        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token}).status_code == 204
        return user, change, key, reset, holder

    def test_the_link_puts_the_previous_address_back_and_secures_the_account(self, client, committed_sessions, sign_in):
        user, change, key, _, holder = self._confirmed_change(client, committed_sessions, sign_in)
        with committed_sessions() as db:
            reset = make_reset_token(db, user)
            db.commit()

        response = client.post(f"{_PUBLIC}/email-change/cancel", json={"token": change.revert_token})

        assert response.status_code == 200
        assert response.json() == {"change_applied": True, "email_restored": True}
        assert _user_row(committed_sessions, user.id).email == user.email
        assert holder.client.get(_PROFILE).status_code == 401
        with committed_sessions() as db:
            assert db.get(sessions_models.UsersSessions, holder.session_id) is None
            revoked = db.scalars(
                sa.select(api_keys_models.UsersApiKeys.revoked_at).where(api_keys_models.UsersApiKeys.id == key.id)
            ).one()
            assert revoked is not None
            assert set(
                db.scalars(
                    sa.select(reset_models.PasswordResetToken.used).where(
                        reset_models.PasswordResetToken.user_id == user.id
                    )
                )
            ) == {True}
        assert (
            client.post(
                f"{_PUBLIC}/password-reset/confirm", json={"token": reset, "password": _CHOSEN_PASSWORD}
            ).status_code
            == 400
        )
        rows = audit_rows(committed_sessions, sign_up_audit_actions.EMAIL_CHANGE_CANCEL)
        assert [(row.outcome, row.target_id) for row in rows] == [("success", str(user.id))]
        assert rows[0].details == {
            "sessions_revoked": 1,
            "api_keys_revoked": 1,
            "change_applied": True,
            "email_restored": True,
            "reset_tokens_revoked": True,
        }

    def test_the_link_works_once(self, client, committed_sessions, sign_in):
        _, change, *_ = self._confirmed_change(client, committed_sessions, sign_in)

        first = client.post(f"{_PUBLIC}/email-change/cancel", json={"token": change.revert_token})
        second = client.post(f"{_PUBLIC}/email-change/cancel", json={"token": change.revert_token})

        assert (first.status_code, second.status_code) == (200, 400)
        rows = audit_rows(committed_sessions, sign_up_audit_actions.EMAIL_CHANGE_CANCEL)
        assert [(row.outcome, row.target_id) for row in rows] == [("success", rows[0].target_id), ("failure", None)]

    def test_a_link_used_before_the_change_is_confirmed_voids_the_confirmation(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "new-address@example.com")
            db.commit()

        cancelled = client.post(f"{_PUBLIC}/email-change/cancel", json={"token": change.revert_token})
        confirmed = client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token})

        assert cancelled.json() == {"change_applied": False, "email_restored": False}
        assert confirmed.status_code == 400
        assert _user_row(committed_sessions, user.id).email == user.email

    def test_a_link_after_the_revert_window_is_refused(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "new-address@example.com", revert_window=-timedelta(seconds=1))
            db.commit()

        response = client.post(f"{_PUBLIC}/email-change/cancel", json={"token": change.revert_token})

        assert response.status_code == 400
        assert response.json()["type"] == _INVALID_INPUT
        rows = audit_rows(committed_sessions, sign_up_audit_actions.EMAIL_CHANGE_CANCEL)
        assert [(row.outcome, row.target_id) for row in rows] == [("failure", None)]

    def test_a_forged_link_is_refused(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, "new-address@example.com")
            db.commit()
        forged = f"{change.change_id}.{'0' * 43}"

        assert client.post(f"{_PUBLIC}/email-change/cancel", json={"token": forged}).status_code == 400
        assert client.post(f"{_PUBLIC}/email-change/cancel", json={"token": "garbage"}).status_code == 400

    def test_the_previous_address_is_not_restored_while_another_account_holds_it(
        self, client, committed_sessions, sign_in
    ):
        user, change, *_ = self._confirmed_change(client, committed_sessions, sign_in)
        with committed_sessions() as db:
            make_user(db, email=user.email)
            db.commit()

        response = client.post(f"{_PUBLIC}/email-change/cancel", json={"token": change.revert_token})

        assert response.json() == {"change_applied": True, "email_restored": False}
        assert _user_row(committed_sessions, user.id).email == "new-address@example.com"

    def test_the_previous_address_stays_reserved_during_the_revert_window(self, client, committed_sessions, sign_in):
        user, *_ = self._confirmed_change(client, committed_sessions, sign_in)

        with committed_sessions() as db:
            assert sign_up_service.get_email_reserver_id(user.email, None, db) == user.id
