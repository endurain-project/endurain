"""An identity-provider sign-in of an account with MFA finishes at ``/auth/mfa/verify``, like a password sign-in.

The exchange checks the session, the verifier and the client type, then answers the ``mfa`` step without using the
session up. The verify claims the challenge and then the session, each once, and issues the session's tokens.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jasil.testing as jasil_testing
import pytest
from sqlalchemy import func, select, update

import core.dependencies as core_dependencies
import core.network as core_network
import modules.auth.constants as auth_constants
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
import modules.auth.sessions.integration_service as sessions_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.models as users_models
from tests.auth.authentication.conftest import (
    BACKUP_CODE,
    MOBILE,
    PASSWORD,
    SSO_VERIFIER,
    USER_ID,
    USERNAME,
    WEB,
    create_sso_session,
)

_WRONG = "000000"
_LOGIN = "auth.session.login"
_SESSION_ENDED = "urn:endurain:error:session-ended"

pytestmark = pytest.mark.usefixtures("aware_session_expiry")


def _store() -> pending_login_store.PendingMFALogin:
    return pending_login_store.PendingMFALogin(core_dependencies.get_platform_state())


def _exchange(stack, session_id, headers=WEB, ip=None, **body):
    url = f"/auth/sessions/{session_id}/tokens"
    json = {"code_verifier": SSO_VERIFIER, **body}
    if ip is None:
        return stack.client.post(url, json=json, headers=headers)
    with patch.object(core_network, "get_ip_address", return_value=ip):
        return stack.client.post(url, json=json, headers=headers)


def _challenge(stack, session_id, headers=WEB, ip=None) -> str:
    response = _exchange(stack, session_id, headers, ip)
    assert response.status_code == 200, response.text
    return response.json()["mfa_challenge"]


def _verify(stack, challenge, code=BACKUP_CODE, headers=WEB, ip=None):
    body = {"mfa_challenge": challenge, "mfa_code": code}
    if ip is None:
        return stack.client.post("/auth/mfa/verify", json=body, headers=headers)
    with patch.object(core_network, "get_ip_address", return_value=ip):
        return stack.client.post("/auth/mfa/verify", json=body, headers=headers)


def _session(stack, session_id) -> sessions_models.UsersSessions:
    with stack.factory() as db:
        row = db.get(sessions_models.UsersSessions, session_id)
        assert row is not None
        db.expunge(row)
        return row


def _sessions(stack) -> int:
    with stack.factory() as db:
        return db.execute(select(func.count()).select_from(sessions_models.UsersSessions)).scalar_one()


def _unused_codes(stack) -> int:
    with stack.factory() as db:
        return len(backup_codes_crud.get_user_unused_backup_codes(USER_ID, db))


def _assert_unclaimed(stack, session_id) -> None:
    row = _session(stack, session_id)
    assert row.tokens_exchanged is False
    assert row.refresh_token is None
    assert row.oauth_state_id is not None


def _refusal(audit, reason: str) -> dict:
    entry = audit.assert_audited(_LOGIN, outcome="failure", target_type="user", target_id=str(USER_ID))
    assert entry.details["method"] == "identity_provider"
    assert entry.details["reason"] == reason
    assert entry.details["mfa"] is True
    return entry.details


class TestExchange:
    """The exchange of an MFA account's session answers the MFA step and leaves the session unused."""

    @pytest.mark.parametrize(("client_type", "headers"), [("web", WEB), ("mobile", MOBILE)])
    def test_the_exchange_answers_the_mfa_step_and_does_not_claim_the_session(
        self, mfa_plain_signin, client_type, headers
    ):
        session_id = create_sso_session(mfa_plain_signin, auth_constants.ClientType(client_type))

        response = _exchange(mfa_plain_signin, session_id, headers)

        body = response.json()
        assert response.status_code == 200
        assert body.keys() == {"next_step", "mfa_challenge", "methods"}
        assert body["next_step"] == "mfa"
        assert body["methods"] == ["totp", "backup_code"]
        assert "set-cookie" not in response.headers
        assert response.headers["cache-control"] == "no-store"
        _assert_unclaimed(mfa_plain_signin, session_id)

    def test_the_challenge_records_the_session_client_type_network_and_generation(
        self, mfa_plain_signin, security_generations
    ):
        session_id = create_sso_session(mfa_plain_signin, auth_constants.ClientType.MOBILE)

        challenge = _challenge(mfa_plain_signin, session_id, MOBILE, ip="203.0.113.5")

        assert _store().get_pending_login(challenge) == pending_login_store.PendingLogin(
            user_id=USER_ID,
            client_type=auth_constants.ClientType.MOBILE,
            code_challenge=None,
            code_challenge_method=None,
            client_network="203.0.113.5",
            security_generation=0,
            sso_session_id=session_id,
        )

    def test_an_mfa_code_in_the_exchange_body_is_refused(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)

        response = _exchange(mfa_plain_signin, session_id, mfa_code=BACKUP_CODE)

        assert response.status_code == 422
        assert _unused_codes(mfa_plain_signin) == 1
        _assert_unclaimed(mfa_plain_signin, session_id)

    def test_a_wrong_verifier_issues_no_challenge(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)

        with patch.object(pending_login_store.PendingMFALogin, "add_pending_login") as add:
            response = mfa_plain_signin.client.post(
                f"/auth/sessions/{session_id}/tokens", json={"code_verifier": "w" * 43}, headers=WEB
            )

        assert response.status_code == 400
        add.assert_not_called()

    def test_an_exchange_while_a_challenge_is_pending_issues_a_fresh_one(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)

        first, second = _challenge(mfa_plain_signin, session_id), _challenge(mfa_plain_signin, session_id)

        assert first != second
        assert _verify(mfa_plain_signin, second).status_code == 200

    def test_an_account_without_mfa_still_gets_its_tokens_from_the_exchange(self, plain_signin):
        session_id = create_sso_session(plain_signin)

        with jasil_testing.capture_audit() as audit:
            response = _exchange(plain_signin, session_id)

        assert response.status_code == 200
        assert response.json()["next_step"] == "tokens"
        assert "endurain_refresh_token" in response.headers["set-cookie"]
        row = _session(plain_signin, session_id)
        assert row.tokens_exchanged is True
        assert row.amr == ["fed"]
        entry = audit.assert_audited(_LOGIN, outcome="success")
        assert entry.details["method"] == "identity_provider"
        assert entry.details["mfa"] is False


class TestVerifyCompletesTheSession:
    def test_a_web_sign_in_gets_the_sessions_tokens_and_cookies(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)

        with jasil_testing.capture_audit() as audit:
            response = _verify(mfa_plain_signin, challenge)

        body = response.json()
        assert response.status_code == 200
        assert body["next_step"] == "tokens"
        assert body["session_id"] == str(session_id)
        assert "refresh_token" not in body
        cookies = response.headers.get_list("set-cookie")
        assert any("endurain_refresh_token" in cookie for cookie in cookies)
        assert any("endurain_device" in cookie for cookie in cookies)
        row = _session(mfa_plain_signin, session_id)
        assert row.tokens_exchanged is True
        assert row.oauth_state_id is None
        assert row.device_hash is not None
        assert row.amr == ["fed", "otp", "mfa"]
        assert _sessions(mfa_plain_signin) == 1
        assert _unused_codes(mfa_plain_signin) == 0
        entry = audit.assert_audited(_LOGIN, outcome="success", target_type="user", target_id=str(USER_ID))
        assert entry.details["method"] == "identity_provider"
        assert entry.details["mfa"] is True

    def test_a_mobile_sign_in_gets_every_token_and_its_device_id_in_the_body(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin, auth_constants.ClientType.MOBILE)
        challenge = _challenge(mfa_plain_signin, session_id, MOBILE)

        response = _verify(mfa_plain_signin, challenge, headers=MOBILE)

        body = response.json()
        assert response.status_code == 200
        assert body["next_step"] == "tokens"
        assert body["session_id"] == str(session_id)
        assert body["refresh_token"]
        assert len(body["device_id"]) == 43
        assert "set-cookie" not in response.headers
        assert _session(mfa_plain_signin, session_id).tokens_exchanged is True

    def test_the_exchange_after_the_sign_in_finds_the_session_used_up(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        assert _verify(mfa_plain_signin, _challenge(mfa_plain_signin, session_id)).status_code == 200

        assert _exchange(mfa_plain_signin, session_id).status_code == 404

    def test_the_challenge_finishes_the_sign_in_once(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)
        assert _verify(mfa_plain_signin, challenge).status_code == 200

        replay = _verify(mfa_plain_signin, challenge)

        assert replay.status_code == 401
        assert replay.json()["type"] == _SESSION_ENDED

    def test_a_second_challenge_for_a_session_another_one_finished_is_refused_before_its_code(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        first, second = _challenge(mfa_plain_signin, session_id), _challenge(mfa_plain_signin, session_id)
        assert _verify(mfa_plain_signin, first).status_code == 200

        with (
            jasil_testing.capture_audit() as audit,
            patch("modules.auth.mfa.integration_service.verify_user_mfa", return_value=True) as verify,
        ):
            response = _verify(mfa_plain_signin, second, "123456")

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED
        verify.assert_not_called()
        _refusal(audit, "sso_session_ended")
        assert _store().get_pending_login(second) is None

    def test_a_session_claimed_while_the_code_was_checked_is_refused_and_keeps_the_backup_code(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)

        with (
            jasil_testing.capture_audit() as audit,
            patch("modules.auth.sessions.integration_service.claim_session_for_token_exchange", return_value=None),
        ):
            response = _verify(mfa_plain_signin, challenge)

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED
        assert "set-cookie" not in response.headers
        _refusal(audit, "sso_session_ended")
        assert _unused_codes(mfa_plain_signin) == 1


class TestWrongCodes:
    def test_a_wrong_code_is_counted_and_leaves_the_session_and_the_challenge_usable(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)

        with (
            jasil_testing.capture_audit() as audit,
            patch.object(
                pending_login_store.PendingMFALogin,
                "record_failed_attempt",
                return_value=pending_login_store.FailedMfaRecord(count=1, account_locked_now=False),
            ) as record_failed,
        ):
            response = _verify(mfa_plain_signin, challenge, _WRONG)

        assert response.status_code == 400
        assert response.json()["type"] == "urn:endurain:error:invalid-mfa-code"
        record_failed.assert_called_once_with(USERNAME, "testclient", user_id=USER_ID)
        _refusal(audit, "invalid_mfa_code")
        _assert_unclaimed(mfa_plain_signin, session_id)
        assert _verify(mfa_plain_signin, challenge).status_code == 200

    def test_the_third_wrong_code_ends_the_challenge(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)

        statuses = [_verify(mfa_plain_signin, challenge, _WRONG).status_code for _ in range(3)]

        assert statuses == [400, 400, 401]
        assert _verify(mfa_plain_signin, challenge).status_code == 401
        _assert_unclaimed(mfa_plain_signin, session_id)
        assert _unused_codes(mfa_plain_signin) == 1

    def test_a_locked_out_account_is_refused_before_the_code_is_checked(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)

        with (
            jasil_testing.capture_audit() as audit,
            patch.object(pending_login_store.PendingMFALogin, "is_locked_out", return_value=True),
            patch.object(
                pending_login_store.PendingMFALogin,
                "get_lockout_time",
                return_value=datetime.now(UTC) + timedelta(minutes=5),
            ),
        ):
            response = _verify(mfa_plain_signin, challenge)

        assert response.status_code == 429
        entry = audit.assert_audited(_LOGIN, outcome="denied")
        assert entry.details["method"] == "identity_provider"
        assert entry.details["reason"] == "locked_out"
        assert _unused_codes(mfa_plain_signin) == 1
        _assert_unclaimed(mfa_plain_signin, session_id)


class TestChallengeBinding:
    def test_a_challenge_presented_from_another_network_is_refused_and_stays_usable_from_its_own(
        self, mfa_plain_signin
    ):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id, ip="203.0.113.5")

        with jasil_testing.capture_audit() as audit:
            response = _verify(mfa_plain_signin, challenge, ip="198.51.100.9")

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED
        _refusal(audit, "mfa_challenge_network_mismatch")
        _assert_unclaimed(mfa_plain_signin, session_id)
        assert _verify(mfa_plain_signin, challenge, ip="203.0.113.5").status_code == 200

    def test_a_challenge_presented_by_the_other_client_type_is_refused(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)

        assert _verify(mfa_plain_signin, challenge, headers=MOBILE).status_code == 401
        _assert_unclaimed(mfa_plain_signin, session_id)


class TestSessionNoLongerEligible:
    """A session that cannot be exchanged any more ends its challenge with ``session-ended``, before any code."""

    def _refused(self, stack, challenge):
        with (
            jasil_testing.capture_audit() as audit,
            patch.object(pending_login_store.PendingMFALogin, "record_failed_attempt") as record_failed,
        ):
            response = _verify(stack, challenge)
        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED
        assert "set-cookie" not in response.headers
        record_failed.assert_not_called()
        assert _unused_codes(stack) == 1
        assert _store().get_pending_login(challenge) is None
        return audit

    def test_a_security_change_after_the_exchange_refuses_the_code(self, mfa_plain_signin, security_generations):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)
        security_generations.stage_bump(USER_ID, None)

        audit = self._refused(mfa_plain_signin, challenge)

        _refusal(audit, "security_changed")
        _assert_unclaimed(mfa_plain_signin, session_id)

    def test_a_deactivation_after_the_exchange_refuses_the_code(self, mfa_plain_signin, security_generations):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)
        # Deactivation bumps the account's security generation in the transaction that deactivates it.
        security_generations.stage_bump(USER_ID, None)
        with mfa_plain_signin.factory() as db:
            db.execute(update(users_models.Users).where(users_models.Users.id == USER_ID).values(active=False))
            db.commit()

        self._refused(mfa_plain_signin, challenge)

        _assert_unclaimed(mfa_plain_signin, session_id)

    def test_a_session_that_was_deleted_after_the_exchange_refuses_the_code(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)
        with mfa_plain_signin.factory() as db:
            sessions_integration.delete_session(session_id, USER_ID, db)
            db.commit()

        audit = self._refused(mfa_plain_signin, challenge)

        _refusal(audit, "sso_session_ended")
        assert _sessions(mfa_plain_signin) == 0

    def test_a_session_that_expired_after_the_exchange_refuses_the_code(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)
        with mfa_plain_signin.factory() as db:
            db.execute(
                update(sessions_models.UsersSessions)
                .where(sessions_models.UsersSessions.id == session_id)
                .values(expires_at=datetime(2000, 1, 1, tzinfo=UTC))
            )
            db.commit()

        audit = self._refused(mfa_plain_signin, challenge)

        _refusal(audit, "sso_session_ended")


class TestPasswordAndSsoChallengesStayApart:
    def test_a_password_challenge_creates_its_own_session_and_leaves_the_sso_session_unused(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        _challenge(mfa_plain_signin, session_id)
        password_challenge = mfa_plain_signin.client.post(
            "/auth/login", data={"username": USERNAME, "password": PASSWORD}, headers=WEB
        ).json()["mfa_challenge"]

        response = _verify(mfa_plain_signin, password_challenge)

        assert response.status_code == 200
        assert response.json()["session_id"] != str(session_id)
        assert _sessions(mfa_plain_signin) == 2
        _assert_unclaimed(mfa_plain_signin, session_id)

    def test_an_sso_challenge_finishes_only_its_own_session(self, mfa_plain_signin):
        session_id = create_sso_session(mfa_plain_signin)
        other_session_id = create_sso_session(mfa_plain_signin)
        challenge = _challenge(mfa_plain_signin, session_id)

        response = _verify(mfa_plain_signin, challenge)

        assert response.json()["session_id"] == str(session_id)
        assert _sessions(mfa_plain_signin) == 2
        _assert_unclaimed(mfa_plain_signin, other_session_id)
