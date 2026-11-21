"""A security change that commits while the password is verified outdates the proof the sign-in creates."""

import pytest
import sqlalchemy as sa
from pwdlib import PasswordHash

import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
from tests._factories.tokens import audit_rows
from tests.auth.authentication.conftest import (
    MOBILE,
    PASSWORD_CHANGE,
    WEB,
    exchange,
    login,
    pending_mfa_store,
    session_count,
    verify,
)

_REFUSAL = "Unable to authenticate with provided credentials"


@pytest.fixture
def reset_during_the_hash(monkeypatch, committed_sessions):
    """Return a function that commits a security change of an account while its password is being verified.

    The password hash check is the third-party step the change lands in; the real check still runs afterwards.
    """

    def arm(account) -> None:
        original = PasswordHash.verify_and_update

        def verify_and_update(self, password, stored_hash):
            with committed_sessions() as db:
                security_generation_integration.stage_bump(account.user.id, db)
                db.commit()
            return original(self, password, stored_hash)

        monkeypatch.setattr(PasswordHash, "verify_and_update", verify_and_update)

    return arm


def _generation(sessions, account) -> int:
    with sessions() as db:
        return security_generation_integration.current_generation(account.user.id, db)


def _stamp_of_session(sessions, session_id) -> int | None:
    with sessions() as db:
        return db.scalar(
            sa.select(oauth_state_models.OAuthState.security_generation)
            .join(
                sessions_models.UsersSessions,
                sessions_models.UsersSessions.oauth_state_id == oauth_state_models.OAuthState.id,
            )
            .where(sessions_models.UsersSessions.id == session_id)
        )


class TestWebSignIn:
    def test_a_reset_that_commits_during_the_hash_leaves_a_web_sign_in_without_a_session(
        self, client, committed_sessions, account, reset_during_the_hash
    ):
        reset_during_the_hash(account)

        response = login(client, account)

        assert response.status_code == 401
        assert response.json()["detail"] == _REFUSAL
        assert response.headers["www-authenticate"] == "Session"
        assert session_count(committed_sessions, account.user.id) == 0
        row = audit_rows(committed_sessions, login_audit_actions.LOGIN)[-1]
        assert (row.outcome, row.target_id) == ("failure", str(account.user.id))
        assert row.details["reason"] == "security_changed"


class TestChallengesCarryTheGenerationReadBeforeTheHash:
    def test_the_mfa_challenge_is_outdated_by_a_change_during_the_hash(
        self, client, committed_sessions, mfa_account, reset_during_the_hash
    ):
        reset_during_the_hash(mfa_account)

        challenge = login(client, mfa_account).json()["mfa_challenge"]

        pending = pending_mfa_store().get_pending_login(challenge)
        assert pending is not None
        assert pending.security_generation == _generation(committed_sessions, mfa_account) - 1
        assert verify(client, challenge, mfa_account.backup_code).status_code == 401
        assert session_count(committed_sessions, mfa_account.user.id) == 0

    def test_the_forced_change_challenge_is_outdated_by_a_change_during_the_hash(
        self, client, committed_sessions, must_change_account, reset_during_the_hash
    ):
        reset_during_the_hash(must_change_account)

        challenge = login(client, must_change_account).json()["password_change_challenge"]

        response = client.post(
            PASSWORD_CHANGE,
            json={"password_change_challenge": challenge, "password": "A-brand-new-passphrase-42!"},
            headers=WEB,
        )
        assert response.status_code == 401
        assert session_count(committed_sessions, must_change_account.user.id) == 0

    def test_the_mobile_session_is_outdated_by_a_change_during_the_hash(
        self, client, committed_sessions, account, reset_during_the_hash
    ):
        reset_during_the_hash(account)

        session_id = login(client, account, MOBILE).json()["session_id"]

        assert _stamp_of_session(committed_sessions, session_id) == _generation(committed_sessions, account) - 1
        assert exchange(client, session_id).status_code == 404


class TestMfaStepCarriesTheChallengesStamp:
    def test_the_mobile_session_is_stamped_with_the_generation_the_challenge_was_issued_under(
        self, client, committed_sessions, mfa_account
    ):
        with committed_sessions() as db:
            security_generation_integration.stage_bump(mfa_account.user.id, db)
            db.commit()
        challenge = login(client, mfa_account, MOBILE).json()["mfa_challenge"]

        session_id = verify(client, challenge, mfa_account.backup_code, MOBILE).json()["session_id"]

        assert _stamp_of_session(committed_sessions, session_id) == _generation(committed_sessions, mfa_account)
