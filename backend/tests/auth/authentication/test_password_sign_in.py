"""A password sign-in answers its next step, refuses every failure with one answer, and audits each outcome."""

import pytest
import sqlalchemy as sa
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.sessions.models as sessions_models
import modules.users.users.schema as users_schema
from modules.auth.access_tokens.contracts import TokenType
from tests._factories.server_settings import edit_server_settings
from tests._factories.tokens import audit_rows
from tests._factories.users import make_user
from tests.auth.authentication.conftest import (
    LOGIN,
    MOBILE,
    WEB,
    Account,
    from_address,
    login,
    make_account,
    session_count,
)

_BCRYPT_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO5lC7Zq3o1m1u0YF1kXJq8r9eJ8q7y6e"
_COMPOSED = "caf\u00e9-au-lait-noir"
_DECOMPOSED = "cafe\u0301-au-lait-noir"
_REFUSAL = "Unable to authenticate with provided credentials"


def _logins(committed_sessions):
    return audit_rows(committed_sessions, login_audit_actions.LOGIN)


def _problem(response) -> dict:
    """The problem body without the per-request id."""
    return {k: v for k, v in response.json().items() if k != "request_id"}


def _set_password(committed_sessions, account: Account, password_hash: str) -> None:
    with committed_sessions() as db:
        credentials_integration.set_local_password_hash(account.user.id, password_hash, db, change_required=False)
        db.commit()


class TestWebSignIn:
    def test_a_correct_password_answers_tokens_a_refresh_cookie_and_a_session(
        self, client, committed_sessions, account
    ):
        response = login(client, account)

        body = response.json()
        assert response.status_code == 200
        assert body["next_step"] == "tokens"
        assert body["token_type"] == "bearer"
        assert "refresh_token" not in body
        assert "endurain_refresh_token" in response.headers["set-cookie"]
        assert response.headers["cache-control"] == "no-store"
        assert session_count(committed_sessions, account.user.id) == 1

    def test_the_access_token_is_accepted_by_a_protected_route(self, client, account):
        token = login(client, account).json()["access_token"]

        profile = client.get("/api/v1/profile", headers={**WEB, "Authorization": f"Bearer {token}"})

        assert profile.status_code == 200
        assert profile.json()["id"] == str(account.user.id)

    def test_the_tokens_name_the_clients_type(self, client, account):
        response = login(client, account)

        manager = access_tokens_integration.get_token_manager()
        token = response.json()["access_token"]
        manager.validate_token_expiration(token, TokenType.ACCESS)
        assert manager.get_token_claim(token, "client_type", TokenType.ACCESS) == "web"

    def test_the_sign_in_is_audited_as_a_success_of_the_user(self, client, committed_sessions, account):
        login(client, account)

        (row,) = _logins(committed_sessions)
        assert (row.outcome, row.target_id, row.actor_id) == ("success", str(account.user.id), str(account.user.id))
        assert row.details["method"] == "password"
        assert row.details["mfa"] is False

    def test_the_username_is_trimmed_before_it_is_looked_up(self, client, account):
        response = login(client, account, username=f"  {account.username}  ")

        assert response.status_code == 200

    def test_a_password_set_composed_signs_in_typed_decomposed(self, client, committed_sessions, account):
        _set_password(
            committed_sessions, account, credentials_integration.get_password_hasher().hash_password(_COMPOSED)
        )

        response = login(client, account, password=_DECOMPOSED)

        assert response.status_code == 200

    def test_a_hash_of_the_raw_non_nfc_text_does_not_sign_in(self, client, committed_sessions, account):
        raw_hash = credentials_integration.get_password_hasher().hash_password(_DECOMPOSED)
        _set_password(committed_sessions, account, raw_hash)

        assert login(client, account, password=_DECOMPOSED).status_code == 401

    def test_a_bcrypt_hash_is_refused_like_a_wrong_password(self, client, committed_sessions, account):
        _set_password(committed_sessions, account, _BCRYPT_HASH)

        response = login(client, account, password="x" * 100)

        assert response.status_code == 401
        assert response.json()["detail"] == _REFUSAL


class TestRefusals:
    def test_a_wrong_password_is_a_401_audited_against_the_user(self, client, committed_sessions, account):
        response = login(client, account, password="not the password")

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Session"
        assert response.json()["detail"] == _REFUSAL
        (row,) = _logins(committed_sessions)
        assert (row.outcome, row.target_id) == ("failure", str(account.user.id))
        assert row.details["reason"] == "invalid_credentials"
        assert account.username not in repr(row.details)
        assert session_count(committed_sessions, account.user.id) == 0

    def test_an_unknown_username_is_answered_like_a_wrong_password_and_audited_without_a_target(
        self, client, committed_sessions, account
    ):
        wrong = login(client, account, password="not the password")

        unknown = login(client, account, username="nobody-by-that-name")

        assert (unknown.status_code, _problem(unknown), unknown.headers["www-authenticate"]) == (
            wrong.status_code,
            _problem(wrong),
            wrong.headers["www-authenticate"],
        )
        row = _logins(committed_sessions)[-1]
        assert row.target_id is None
        assert "nobody-by-that-name" not in repr(row.details)

    def test_an_account_without_a_local_password_is_answered_like_a_wrong_password(self, client, committed_sessions):
        with committed_sessions() as db:
            sso_only = make_user(db, with_password=False)
            db.commit()

        response = client.post(LOGIN, data={"username": sso_only.username, "password": "anything"}, headers=WEB)

        assert response.status_code == 401
        assert response.json()["detail"] == _REFUSAL
        (row,) = _logins(committed_sessions)
        assert row.target_id == str(sso_only.id)

    def test_an_inactive_account_is_refused_alike_even_with_the_right_password(self, client, committed_sessions):
        inactive = make_account(committed_sessions, active=False)

        response = login(client, inactive)

        assert response.status_code == 401
        assert response.json()["detail"] == _REFUSAL
        (row,) = _logins(committed_sessions)
        assert (row.outcome, row.target_id) == ("denied", str(inactive.user.id))
        assert row.details["reason"] == "inactive"
        assert session_count(committed_sessions, inactive.user.id) == 0

    def test_local_sign_in_turned_off_refuses_a_regular_user_but_admits_an_administrator(
        self, client, committed_sessions
    ):
        regular = make_account(committed_sessions)
        admin = make_account(committed_sessions, access_type=users_schema.UserAccessType.ADMIN)
        with committed_sessions() as db:
            edit_server_settings(db, local_login_enabled=False)
            db.commit()

        refused = login(client, regular)
        admitted = login(client, admin)

        assert refused.status_code == 401
        assert refused.json()["detail"] == _REFUSAL
        assert admitted.status_code == 200
        row = next(r for r in _logins(committed_sessions) if r.outcome == "denied")
        assert (row.target_id, row.details["reason"]) == (str(regular.user.id), "password_sign_in_disabled")

    def test_a_refused_sign_in_leaves_no_session_row(self, client, committed_sessions, account):
        login(client, account, password="wrong")

        with committed_sessions() as db:
            assert db.scalar(sa.select(sa.func.count()).select_from(sessions_models.UsersSessions)) == 0

    def test_five_wrong_passwords_lock_the_client_and_audit_the_next_attempt_as_denied(
        self, app, committed_sessions, account
    ):
        client = from_address(app, "203.0.113.5")
        for _ in range(5):
            assert login(client, account, password="wrong").status_code == 401

        locked = login(client, account)

        assert locked.status_code == 429
        assert int(locked.headers["retry-after"]) > 0
        row = _logins(committed_sessions)[-1]
        assert (row.outcome, row.details["reason"]) == ("denied", "locked_out")
        assert login(from_address(app, "198.51.100.9"), account).status_code == 200


class TestClientTypeHeader:
    @pytest.mark.parametrize("headers", [{"X-Client-Type": "ios"}, {"X-Client-Type": "Web"}, {}])
    def test_login_answers_422_for_a_missing_or_unknown_client_type(self, client, account, headers):
        response = client.post(
            LOGIN, data={"username": account.username, "password": account.password}, headers=headers
        )

        assert response.status_code == 422
        assert response.json()["type"] == "urn:endurain:error:validation-failed"
        assert any("X-Client-Type" in str(error["field"]) for error in response.json()["errors"])

    @pytest.mark.parametrize("headers", [{}, {"X-Client-Type": "ios"}])
    def test_a_protected_route_answers_401_before_it_looks_at_the_client_type(self, client, headers):
        response = client.get("/api/v1/profile", headers=headers)

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_a_protected_route_does_not_need_the_header(self, client):
        response = client.get("/api/v1/profile", headers={"Authorization": "Bearer not-a-jwt"})

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'


class TestMobileSignIn:
    def test_a_mobile_sign_in_answers_an_exchange_session_and_never_tokens(self, client, committed_sessions, account):
        body = login(client, account, MOBILE).json()

        assert body["next_step"] == "exchange"
        assert set(body) == {"next_step", "session_id", "device_id"}
        assert session_count(committed_sessions, account.user.id) == 1


class TestMobileSignInAudit:
    def test_a_mobile_sign_in_is_audited_as_a_success_like_a_web_one(self, client, committed_sessions, account):
        login(client, account, MOBILE)

        (row,) = _logins(committed_sessions)
        assert (row.outcome, row.target_id) == ("success", str(account.user.id))
        assert row.details["method"] == "password"


class TestRehash:
    """A hash made with weaker parameters than the configured ones is replaced when its password signs in."""

    @staticmethod
    def _weak_hash(password: str) -> str:
        return PasswordHash([Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1)]).hash(password)

    def test_a_sign_in_replaces_the_hash_and_keeps_whether_the_owner_must_change_it(
        self, client, committed_sessions, must_change_account
    ):
        weak = self._weak_hash(must_change_account.password)
        with committed_sessions() as db:
            credentials_integration.set_local_password_hash(must_change_account.user.id, weak, db, change_required=True)
            db.commit()

        response = login(client, must_change_account)

        credential = _credential(committed_sessions, must_change_account)
        assert response.json()["next_step"] == "password_change"
        assert credential.password_hash != weak
        assert credential.password_change_required is True
        assert _signs_in_with(committed_sessions, must_change_account.password, must_change_account)

    def test_an_mfa_account_has_the_replacement_committed_at_the_password_step(
        self, client, committed_sessions, mfa_account
    ):
        weak = self._weak_hash(mfa_account.password)
        _set_password(committed_sessions, mfa_account, weak)

        assert login(client, mfa_account).json()["next_step"] == "mfa"

        assert _credential(committed_sessions, mfa_account).password_hash != weak

    def test_a_refused_sign_in_leaves_the_hash_as_it_was(self, client, committed_sessions, account):
        weak = self._weak_hash(account.password)
        _set_password(committed_sessions, account, weak)

        assert login(client, account, password="not the password").status_code == 401

        assert _credential(committed_sessions, account).password_hash == weak


def _credential(sessions, account: Account):
    with sessions() as db:
        return credentials_integration.get_credential(account.user.id, db)


def _signs_in_with(sessions, password: str, account: Account) -> bool:
    return credentials_integration.verify_and_update_password(
        password, _credential(sessions, account).password_hash, credentials_integration.get_password_hasher()
    )[0]
