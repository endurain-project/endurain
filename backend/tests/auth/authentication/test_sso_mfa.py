"""An identity-provider sign-in of an account with MFA finishes at the MFA step, which claims the session once."""

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

import core.network as core_network
import modules.auth.constants as auth_constants
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.models as users_models
from tests._factories.tokens import audit_rows
from tests.auth.authentication.conftest import (
    MOBILE,
    WEB,
    WRONG_CODE,
    exchange,
    from_address,
    login,
    make_sso_session,
    pending_mfa_store,
    session_count,
    verify,
)

_SESSION_ENDED = "urn:endurain:error:session-ended"
_LOGINS = login_audit_actions.LOGIN


def _challenge(client, sessions, account, session_id=None, headers=WEB) -> str:
    """Exchange an identity-provider session of the account and return the MFA challenge it answers."""
    if session_id is None:
        session_id = make_sso_session(sessions, account.user)
    return exchange(client, session_id, headers=headers).json()["mfa_challenge"]


def _unused_codes(sessions, account) -> int:
    with sessions() as db:
        return len(backup_codes_crud.get_user_unused_backup_codes(account.user.id, db))


def _session(sessions, session_id) -> sessions_models.UsersSessions | None:
    with sessions() as db:
        return db.get(sessions_models.UsersSessions, session_id)


def _assert_unclaimed(sessions, session_id) -> None:
    row = _session(sessions, session_id)
    assert row is not None and row.tokens_exchanged is False


class TestExchange:
    """The exchange of an MFA account's session answers the MFA step and leaves the session unused."""

    @pytest.mark.parametrize(("client_type", "headers"), [("web", WEB), ("mobile", MOBILE)])
    def test_the_exchange_answers_the_mfa_step_and_does_not_claim_the_session(
        self, client, committed_sessions, mfa_account, client_type, headers
    ):
        session_id = make_sso_session(committed_sessions, mfa_account.user, client_type=client_type)

        response = exchange(client, session_id, headers=headers)

        body = response.json()
        assert response.status_code == 200
        assert body.keys() == {"next_step", "mfa_challenge", "methods"}
        assert body["next_step"] == "mfa"
        assert body["methods"] == ["totp", "backup_code"]
        assert "set-cookie" not in response.headers
        assert response.headers["cache-control"] == "no-store"
        _assert_unclaimed(committed_sessions, session_id)

    def test_the_challenge_records_the_session_client_type_network_generation_and_session(
        self, app, committed_sessions, mfa_account
    ):
        session_id = make_sso_session(committed_sessions, mfa_account.user, client_type="mobile")
        with committed_sessions() as db:
            generation = security_generation_integration.current_generation(mfa_account.user.id, db)

        challenge = _challenge(
            from_address(app, "203.0.113.5"), committed_sessions, mfa_account, session_id, headers=MOBILE
        )

        assert pending_mfa_store().get_pending_login(challenge) == pending_login_store.PendingLogin(
            user_id=mfa_account.user.id,
            client_type=auth_constants.ClientType.MOBILE,
            code_challenge=None,
            code_challenge_method=None,
            client_network=core_network.client_network("203.0.113.5"),
            security_generation=generation,
            sso_session_id=session_id,
        )

    def test_an_mfa_code_in_the_exchange_body_is_refused(self, client, committed_sessions, mfa_account):
        session_id = make_sso_session(committed_sessions, mfa_account.user)

        response = client.post(
            f"/api/v1/auth/sessions/{session_id}/tokens",
            json={"code_verifier": "v" * 43, "mfa_code": mfa_account.backup_code},
            headers=WEB,
        )

        assert response.status_code == 422
        assert _unused_codes(committed_sessions, mfa_account) == 10
        _assert_unclaimed(committed_sessions, session_id)

    def test_a_wrong_verifier_issues_no_challenge(self, client, committed_sessions, mfa_account):
        session_id = make_sso_session(committed_sessions, mfa_account.user)

        response = exchange(client, session_id, "w" * 43, headers=WEB)

        assert response.status_code == 400
        assert "mfa_challenge" not in response.text

    def test_an_exchange_while_a_challenge_is_pending_issues_a_fresh_one(self, client, committed_sessions, mfa_account):
        session_id = make_sso_session(committed_sessions, mfa_account.user)

        first = _challenge(client, committed_sessions, mfa_account, session_id)
        second = _challenge(client, committed_sessions, mfa_account, session_id)

        assert first != second
        assert verify(client, second, mfa_account.backup_code).status_code == 200

    def test_an_account_without_mfa_still_gets_its_tokens_from_the_exchange(self, client, committed_sessions, account):
        session_id = make_sso_session(committed_sessions, account.user)

        response = exchange(client, session_id, headers=WEB)

        assert response.status_code == 200
        assert response.json()["next_step"] == "tokens"
        row = _session(committed_sessions, session_id)
        assert row is not None
        assert (row.tokens_exchanged, row.amr) == (True, ["fed"])

    def test_a_session_of_a_password_sign_in_has_already_passed_mfa(self, client, committed_sessions, mfa_account):
        challenge = login(client, mfa_account, MOBILE).json()["mfa_challenge"]
        session_id = verify(client, challenge, mfa_account.backup_code, MOBILE).json()["session_id"]

        response = exchange(client, session_id)

        assert response.json()["next_step"] == "tokens"


class TestVerifyCompletesTheSession:
    def test_a_web_sign_in_gets_the_sessions_tokens_and_cookies_and_records_the_second_factor(
        self, client, committed_sessions, mfa_account
    ):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        challenge = _challenge(client, committed_sessions, mfa_account, session_id)

        response = verify(client, challenge, mfa_account.backup_code)

        body = response.json()
        assert response.status_code == 200
        assert (body["next_step"], body["session_id"]) == ("tokens", str(session_id))
        assert "refresh_token" not in body
        assert "endurain_refresh_token" in response.headers["set-cookie"]
        row = _session(committed_sessions, session_id)
        assert row is not None
        assert row.tokens_exchanged is True
        assert row.amr == ["fed", "otp", "mfa"]
        (login_row,) = audit_rows(committed_sessions, _LOGINS)
        assert (login_row.outcome, login_row.details["method"], login_row.details["mfa"]) == (
            "success",
            "identity_provider",
            True,
        )
        assert _unused_codes(committed_sessions, mfa_account) == 9

    def test_a_mobile_sign_in_gets_every_token_and_its_device_id_in_the_body(
        self, client, committed_sessions, mfa_account
    ):
        session_id = make_sso_session(committed_sessions, mfa_account.user, client_type="mobile")
        challenge = _challenge(client, committed_sessions, mfa_account, session_id, MOBILE)

        body = verify(client, challenge, mfa_account.backup_code, MOBILE).json()

        assert body["next_step"] == "tokens"
        assert {"access_token", "refresh_token", "device_id"} <= set(body)

    def test_the_exchange_after_the_sign_in_finds_the_session_used_up(self, client, committed_sessions, mfa_account):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        verify(client, _challenge(client, committed_sessions, mfa_account, session_id), mfa_account.backup_code)

        assert exchange(client, session_id, headers=WEB).status_code == 404

    def test_the_challenge_finishes_the_sign_in_once(self, client, committed_sessions, mfa_account):
        challenge = _challenge(client, committed_sessions, mfa_account)
        verify(client, challenge, mfa_account.mfa.backup_codes[0])

        assert verify(client, challenge, mfa_account.mfa.backup_codes[1]).status_code == 401

    def test_a_second_challenge_for_a_session_another_one_finished_is_refused_before_its_code(
        self, client, committed_sessions, mfa_account
    ):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        first = _challenge(client, committed_sessions, mfa_account, session_id)
        second = _challenge(client, committed_sessions, mfa_account, session_id)
        verify(client, first, mfa_account.mfa.backup_codes[0])

        response = verify(client, second, mfa_account.mfa.backup_codes[1])

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED
        assert _unused_codes(committed_sessions, mfa_account) == 9
        row = audit_rows(committed_sessions, _LOGINS)[-1]
        assert (row.outcome, row.details["reason"]) == ("failure", "sso_session_ended")


class TestWrongCodes:
    def test_a_wrong_code_is_counted_and_leaves_the_session_and_the_challenge_usable(
        self, client, committed_sessions, mfa_account
    ):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        challenge = _challenge(client, committed_sessions, mfa_account, session_id)

        wrong = verify(client, challenge, WRONG_CODE)

        assert wrong.status_code == 400
        row = audit_rows(committed_sessions, _LOGINS)[-1]
        assert (row.outcome, row.details["method"], row.details["reason"]) == (
            "failure",
            "identity_provider",
            "invalid_mfa_code",
        )
        _assert_unclaimed(committed_sessions, session_id)
        assert verify(client, challenge, mfa_account.backup_code).status_code == 200

    def test_the_third_wrong_code_ends_the_challenge_and_leaves_the_session_unused(
        self, client, committed_sessions, mfa_account
    ):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        challenge = _challenge(client, committed_sessions, mfa_account, session_id)

        statuses = [verify(client, challenge, WRONG_CODE).status_code for _ in range(3)]

        assert statuses == [400, 400, 401]
        assert verify(client, challenge, mfa_account.backup_code).status_code == 401
        _assert_unclaimed(committed_sessions, session_id)
        assert _unused_codes(committed_sessions, mfa_account) == 10


class TestChallengeBinding:
    def test_a_challenge_presented_from_another_network_is_refused_and_stays_usable_from_its_own(
        self, app, committed_sessions, mfa_account
    ):
        challenge = _challenge(from_address(app, "203.0.113.5"), committed_sessions, mfa_account)

        refused = verify(from_address(app, "198.51.100.9"), challenge, mfa_account.backup_code)

        assert refused.status_code == 401
        row = audit_rows(committed_sessions, _LOGINS)[-1]
        assert (row.details["method"], row.details["reason"]) == ("identity_provider", "mfa_challenge_network_mismatch")
        assert verify(from_address(app, "203.0.113.5"), challenge, mfa_account.backup_code).status_code == 200

    def test_a_challenge_presented_by_the_other_client_type_is_refused(self, client, committed_sessions, mfa_account):
        challenge = _challenge(client, committed_sessions, mfa_account)

        assert verify(client, challenge, mfa_account.backup_code, MOBILE).status_code == 401


class TestSessionNoLongerEligible:
    """A session that cannot be exchanged any more ends its challenge with ``session-ended``, before any code."""

    def _refused(self, client, sessions, account, challenge):
        response = verify(client, challenge, account.backup_code)
        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED
        assert "set-cookie" not in response.headers
        assert _unused_codes(sessions, account) == 10
        assert pending_mfa_store().get_pending_login(challenge) is None
        return audit_rows(sessions, _LOGINS)[-1]

    def test_a_security_change_after_the_exchange_refuses_the_code(self, client, committed_sessions, mfa_account):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        challenge = _challenge(client, committed_sessions, mfa_account, session_id)
        with committed_sessions() as db:
            security_generation_integration.stage_bump(mfa_account.user.id, db)
            db.commit()

        row = self._refused(client, committed_sessions, mfa_account, challenge)

        assert row.details["reason"] == "security_changed"
        _assert_unclaimed(committed_sessions, session_id)

    def test_a_deactivation_after_the_exchange_refuses_the_code(self, client, committed_sessions, mfa_account):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        challenge = _challenge(client, committed_sessions, mfa_account, session_id)
        with committed_sessions() as db:
            # Deactivation bumps the account's security generation in the transaction that deactivates it.
            security_generation_integration.stage_bump(mfa_account.user.id, db)
            db.execute(
                sa.update(users_models.Users).where(users_models.Users.id == mfa_account.user.id).values(active=False)
            )
            db.commit()

        self._refused(client, committed_sessions, mfa_account, challenge)

        _assert_unclaimed(committed_sessions, session_id)

    def test_a_session_that_was_deleted_after_the_exchange_refuses_the_code(
        self, client, committed_sessions, mfa_account
    ):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        challenge = _challenge(client, committed_sessions, mfa_account, session_id)
        with committed_sessions() as db:
            sessions_integration.delete_session(session_id, mfa_account.user.id, db)
            db.commit()

        row = self._refused(client, committed_sessions, mfa_account, challenge)

        assert row.details["reason"] == "sso_session_ended"
        assert session_count(committed_sessions, mfa_account.user.id) == 0

    def test_a_session_that_expired_after_the_exchange_refuses_the_code(self, client, committed_sessions, mfa_account):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        challenge = _challenge(client, committed_sessions, mfa_account, session_id)
        with committed_sessions() as db:
            db.execute(
                sa.update(sessions_models.UsersSessions)
                .where(sessions_models.UsersSessions.id == session_id)
                .values(expires_at=datetime(2000, 1, 1, tzinfo=UTC))
            )
            db.commit()

        row = self._refused(client, committed_sessions, mfa_account, challenge)

        assert row.details["reason"] == "sso_session_ended"


class TestPasswordAndIdentityProviderChallengesStayApart:
    def test_a_password_challenge_creates_its_own_session_and_leaves_the_provider_session_unused(
        self, client, committed_sessions, mfa_account
    ):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        _challenge(client, committed_sessions, mfa_account, session_id)
        password_challenge = login(client, mfa_account).json()["mfa_challenge"]

        response = verify(client, password_challenge, mfa_account.backup_code)

        assert response.status_code == 200
        assert response.json()["session_id"] != str(session_id)
        assert session_count(committed_sessions, mfa_account.user.id) == 2
        _assert_unclaimed(committed_sessions, session_id)

    def test_a_provider_challenge_finishes_only_its_own_session(self, client, committed_sessions, mfa_account):
        session_id = make_sso_session(committed_sessions, mfa_account.user)
        other_session_id = make_sso_session(committed_sessions, mfa_account.user)
        challenge = _challenge(client, committed_sessions, mfa_account, session_id)

        response = verify(client, challenge, mfa_account.backup_code)

        assert response.json()["session_id"] == str(session_id)
        _assert_unclaimed(committed_sessions, other_session_id)
