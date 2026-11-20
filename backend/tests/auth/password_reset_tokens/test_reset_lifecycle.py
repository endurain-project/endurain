"""A password-reset token works once, expires, is replaced by a newer one, and its reset ends the user's sessions."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi.testclient import TestClient

import core.config as core_config
import modules.auth.credentials.models as credentials_models
import modules.auth.password_reset_tokens.audit_actions as reset_audit_actions
import modules.auth.password_reset_tokens.models as reset_models
import modules.auth.sessions.models as sessions_models
from tests._factories.tokens import audit_rows, make_reset_token
from tests._factories.users import PASSWORD, make_user

_PUBLIC = f"{core_config.ROOT_PATH}/public/password-reset"
_LOGIN = f"{core_config.ROOT_PATH}/auth/login"
_PROFILE = f"{core_config.ROOT_PATH}/profile"
_NEW_PASSWORD = "Another-Password-5678!"
_UNUSABLE = "urn:endurain:error:invalid-input"


def _user_with_token(committed_sessions, **token_options):
    with committed_sessions() as db:
        user = make_user(db)
        token = make_reset_token(db, user, **token_options)
        db.commit()
    return user, token


def _confirm(client: TestClient, token: str, password: str = _NEW_PASSWORD):
    return client.post(f"{_PUBLIC}/confirm", json={"token": token, "password": password})


def _sign_in_with(client: TestClient, username: str, password: str):
    return client.post(_LOGIN, data={"username": username, "password": password}, headers={"X-Client-Type": "web"})


def _password_hash(committed_sessions, user_id):
    with committed_sessions() as db:
        return db.scalar(
            sa.select(credentials_models.LocalCredential.password_hash).where(
                credentials_models.LocalCredential.user_id == user_id
            )
        )


class TestSingleUse:
    def test_a_token_resets_the_password_once_and_the_new_password_signs_in(self, client, committed_sessions):
        user, token = _user_with_token(committed_sessions)

        first = _confirm(client, token)
        second = _confirm(client, token, "Yet-Another-Password-9!")

        assert first.status_code == 204
        assert second.status_code == 400
        assert second.json()["type"] == _UNUSABLE
        assert _sign_in_with(client, user.username, _NEW_PASSWORD).status_code == 200
        assert _sign_in_with(client, user.username, PASSWORD).status_code == 401
        assert _sign_in_with(client, user.username, "Yet-Another-Password-9!").status_code == 401

    def test_the_reset_and_the_refused_second_use_are_audited(self, client, committed_sessions):
        user, token = _user_with_token(committed_sessions)

        _confirm(client, token)
        _confirm(client, token)

        rows = audit_rows(committed_sessions, reset_audit_actions.PASSWORD_RESET)
        assert [(row.outcome, row.target_id) for row in rows] == [("success", str(user.id)), ("failure", None)]
        assert rows[0].details == {"unverified_account_cleaned": False}

    def test_validating_a_token_does_not_consume_it(self, client, committed_sessions):
        _, token = _user_with_token(committed_sessions)

        assert client.post(f"{_PUBLIC}/validate", json={"token": token}).status_code == 204
        assert client.post(f"{_PUBLIC}/validate", json={"token": token}).status_code == 204
        assert _confirm(client, token).status_code == 204
        assert client.post(f"{_PUBLIC}/validate", json={"token": token}).status_code == 400

    def test_an_unknown_token_is_refused_and_audited_without_a_target(self, client, committed_sessions):
        response = _confirm(client, "not-a-token")

        assert response.status_code == 400
        assert response.json()["type"] == _UNUSABLE
        rows = audit_rows(committed_sessions, reset_audit_actions.PASSWORD_RESET)
        assert [(row.outcome, row.target_id) for row in rows] == [("failure", None)]


class TestExpiryAndSupersession:
    def test_an_expired_token_is_refused_and_leaves_the_password_alone(self, client, committed_sessions):
        user, token = _user_with_token(committed_sessions, expires_at=datetime.now(UTC) - timedelta(seconds=1))
        before = _password_hash(committed_sessions, user.id)

        response = _confirm(client, token)

        assert response.status_code == 400
        assert client.post(f"{_PUBLIC}/validate", json={"token": token}).status_code == 400
        assert _password_hash(committed_sessions, user.id) == before
        assert _sign_in_with(client, user.username, PASSWORD).status_code == 200
        rows = audit_rows(committed_sessions, reset_audit_actions.PASSWORD_RESET)
        assert [row.outcome for row in rows] == ["failure"]

    def test_a_new_token_supersedes_the_old_one(self, client, committed_sessions):
        user, old = _user_with_token(committed_sessions)
        with committed_sessions() as db:
            new = make_reset_token(db, user)
            db.commit()

        assert _confirm(client, old).status_code == 400
        assert _confirm(client, new).status_code == 204
        with committed_sessions() as db:
            used = db.scalars(
                sa.select(reset_models.PasswordResetToken.used).where(
                    reset_models.PasswordResetToken.user_id == user.id
                )
            ).all()
        assert used == [True, True]


class TestConcurrentClaims:
    def test_two_simultaneous_resets_with_one_token_succeed_once(self, app, committed_sessions):
        user, token = _user_with_token(committed_sessions)
        barrier = threading.Barrier(2)
        passwords = (_NEW_PASSWORD, "Second-Password-4321!")

        def confirm(password: str):
            client = TestClient(app)
            barrier.wait(timeout=10)
            return _confirm(client, token, password)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [future.result(timeout=60) for future in [pool.submit(confirm, p) for p in passwords]]

        assert sorted(response.status_code for response in responses) == [204, 400]
        winner = passwords[[response.status_code for response in responses].index(204)]
        client = TestClient(app)
        assert _sign_in_with(client, user.username, winner).status_code == 200
        rows = audit_rows(committed_sessions, reset_audit_actions.PASSWORD_RESET)
        assert sorted(row.outcome for row in rows) == ["failure", "success"]


class TestSessionsEnded:
    def test_a_reset_ends_the_users_sessions_and_other_users_keep_theirs(self, client, committed_sessions, sign_in):
        user, token = _user_with_token(committed_sessions)
        with committed_sessions() as db:
            bystander = make_user(db)
            db.commit()
        victim = sign_in(user)
        other = sign_in(bystander)
        assert victim.client.get(_PROFILE).status_code == 200

        assert _confirm(client, token).status_code == 204

        assert victim.client.get(_PROFILE).status_code == 401
        assert other.client.get(_PROFILE).status_code == 200
        with committed_sessions() as db:
            assert db.get(sessions_models.UsersSessions, victim.session_id) is None
            assert db.get(sessions_models.UsersSessions, other.session_id) is not None
