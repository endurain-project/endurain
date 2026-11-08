"""An administrator-set password must be changed at the next sign-in, before any session exists."""

from unittest.mock import patch

import jasil.publisher as platform_publisher
import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState
from sqlalchemy import func, select

import core.dependencies as core_dependencies
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.step_up_store as step_up_store
import modules.auth.authentication.pending_password_change_store as pending_store
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.sessions.models as sessions_models
from tests.auth.authentication.conftest import (
    BACKUP_CODE,
    CHALLENGE,
    MOBILE,
    NEW_PASSWORD,
    PASSWORD,
    USER_ID,
    USERNAME,
    WEB,
)

_PASSWORD_CHANGE = "auth.password.change"
_LOGIN = login_audit_actions.LOGIN.id


def _credential(signin):
    with signin.factory() as db:
        return credentials_integration.get_credential(USER_ID, db)


def _sessions(signin) -> int:
    with signin.factory() as db:
        return db.execute(select(func.count()).select_from(sessions_models.UsersSessions)).scalar_one()


def _store() -> pending_store.PendingPasswordChanges:
    return pending_store.PendingPasswordChanges(core_dependencies.get_platform_state())


def _login(signin, headers=WEB):
    pkce = {"code_challenge": CHALLENGE, "code_challenge_method": "S256"} if headers is MOBILE else {}
    return signin.client.post("/auth/login", data={"username": USERNAME, "password": PASSWORD, **pkce}, headers=headers)


def _change(signin, challenge, password=NEW_PASSWORD, headers=WEB):
    return signin.client.post(
        "/auth/password-change",
        json={"password_change_challenge": challenge, "password": password},
        headers=headers,
    )


def _start(signin, headers=WEB) -> str:
    return _login(signin, headers).json()["password_change_challenge"]


class TestSignInOfAFlaggedAccount:
    def test_the_right_password_answers_password_change_and_creates_no_session(self, signin):
        response = _login(signin)

        body = response.json()
        assert response.status_code == 200
        assert body.keys() == {"next_step", "password_change_challenge"}
        assert body["next_step"] == "password_change"
        assert _sessions(signin) == 0
        assert "set-cookie" not in response.headers
        assert response.headers["cache-control"] == "no-store"

    def test_the_challenge_names_the_login(self, signin):
        challenge = _start(signin)

        assert _store().get(challenge) == pending_store.PendingPasswordChange(
            user_id=USER_ID,
            client_type=auth_constants.ClientType.WEB,
            code_challenge=None,
            code_challenge_method=None,
            mfa=False,
        )

    def test_a_mobile_pkce_login_records_the_pkce_values(self, signin):
        challenge = _start(signin, MOBILE)

        record = _store().get(challenge)
        assert record.client_type == auth_constants.ClientType.MOBILE
        assert (record.code_challenge, record.code_challenge_method) == (CHALLENGE, "S256")

    def test_a_wrong_password_still_answers_401(self, signin):
        response = signin.client.post(
            "/auth/login", data={"username": USERNAME, "password": "wrong password"}, headers=WEB
        )

        assert response.status_code == 401

    def test_the_failed_attempt_counters_are_reset_because_the_password_was_right(self, signin):
        with patch("modules.auth.authentication.failed_login_store.FailedLoginAttempts.reset_attempts") as reset:
            _login(signin)

        reset.assert_called_once()

    def test_an_account_that_chose_its_password_signs_in_directly(self, plain_signin):
        assert _login(plain_signin).json()["next_step"] == "tokens"

    def test_with_mfa_the_step_comes_after_the_code_and_remembers_it(self, mfa_signin):
        challenge = _login(mfa_signin).json()["mfa_challenge"]

        response = mfa_signin.client.post(
            "/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": BACKUP_CODE}, headers=WEB
        )

        assert response.json()["next_step"] == "password_change"
        record = _store().get(response.json()["password_change_challenge"])
        assert (record.user_id, record.mfa) == (USER_ID, True)
        assert _sessions(mfa_signin) == 0

    def test_with_mfa_a_wrong_code_does_not_reveal_a_password_change(self, mfa_signin):
        challenge = _login(mfa_signin).json()["mfa_challenge"]

        response = mfa_signin.client.post(
            "/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": "000000"}, headers=WEB
        )

        assert response.status_code == 400
        assert "password_change_challenge" not in response.text


class TestWhoFlagsTheAccount:
    def test_an_administrator_setting_the_password_makes_the_next_sign_in_ask_for_a_new_one(self, plain_signin):
        with plain_signin.factory() as db:
            account_security_service.change_managed_user_password(USER_ID, "set by an administrator 9", db)
            db.commit()

        assert _credential(plain_signin).password_change_required is True
        response = plain_signin.client.post(
            "/auth/login", data={"username": USERNAME, "password": "set by an administrator 9"}, headers=WEB
        )
        assert response.json()["next_step"] == "password_change"

    def test_the_owner_changing_the_password_clears_the_requirement(self, signin):
        with signin.factory() as db:
            account_security_service.stage_change_own_password(
                USER_ID,
                PASSWORD,
                NEW_PASSWORD,
                None,
                step_up_store.StepUpAttempts(MemoryState()),
                db,
                revoke_other_sessions=False,
                current_session_id="session-1",
            )
            db.commit()

        assert _credential(signin).password_change_required is False


class TestPasswordChangeRoute:
    def test_a_web_change_writes_the_password_clears_the_flag_and_signs_in(self, signin):
        challenge = _start(signin)

        with jasil_testing.capture_audit() as audit, patch.object(platform_publisher, "publish_on_commit") as publish:
            response = _change(signin, challenge)

        body = response.json()
        assert response.status_code == 200
        assert body["next_step"] == "tokens"
        assert "csrf_token" in body
        assert "refresh_token" not in body
        assert "refresh_token" in "".join(response.headers.get_list("set-cookie"))
        assert response.headers["cache-control"] == "no-store"
        credential = _credential(signin)
        assert credential.password_change_required is False
        assert credentials_integration.verify_and_update_password(
            NEW_PASSWORD, credential.password_hash, credentials_integration.get_password_hasher()
        )[0]
        assert _sessions(signin) == 1
        audit.assert_audited(_PASSWORD_CHANGE, target_id=str(USER_ID))
        assert audit.assert_audited(_LOGIN, outcome="success").details["mfa"] is False
        changes = [
            call.args[1]["change"]
            for call in publish.call_args_list
            if call.args[0] == account_security_events.ACCOUNT_SECURITY_CHANGED
        ]
        assert changes == ["password_changed"]

    def test_the_change_voids_unused_password_reset_tokens(self, signin):
        challenge = _start(signin)

        with patch(
            "modules.auth.account_security.account_security_service.password_reset_tokens_integration.revoke_unused_tokens"
        ) as revoke:
            _change(signin, challenge)

        revoke.assert_called_once()
        assert revoke.call_args.args[0] == USER_ID

    def test_the_new_password_signs_in_and_the_old_one_does_not(self, signin):
        _change(signin, _start(signin))

        assert (
            signin.client.post(
                "/auth/login", data={"username": USERNAME, "password": NEW_PASSWORD}, headers=WEB
            ).json()["next_step"]
            == "tokens"
        )
        assert _login(signin).status_code == 401

    def test_a_mobile_change_with_a_pkce_record_answers_an_exchange_session(self, signin):
        challenge = _start(signin, MOBILE)

        response = _change(signin, challenge, headers=MOBILE)

        body = response.json()
        assert body["next_step"] == "exchange"
        assert body["session_id"]
        assert "access_token" not in body
        assert _sessions(signin) == 1

    def test_an_mfa_login_is_audited_as_one(self, mfa_signin):
        challenge = _login(mfa_signin).json()["mfa_challenge"]
        step = mfa_signin.client.post(
            "/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": BACKUP_CODE}, headers=WEB
        ).json()["password_change_challenge"]

        with jasil_testing.capture_audit() as audit:
            response = _change(mfa_signin, step)

        assert response.status_code == 200
        assert audit.assert_audited(_LOGIN, outcome="success").details["mfa"] is True

    def test_the_challenge_works_once(self, signin):
        challenge = _start(signin)

        assert _change(signin, challenge).status_code == 200
        assert _change(signin, challenge, "another passphrase 77").status_code == 401

    def test_an_unknown_challenge_is_401_writes_nothing_and_is_audited(self, signin):
        with jasil_testing.capture_audit() as audit:
            response = _change(signin, "u" * 43)

        assert response.status_code == 401
        assert _credential(signin).password_change_required is True
        assert _sessions(signin) == 0
        entry = audit.assert_audited(_LOGIN, outcome="failure")
        assert entry.details["reason"] == login_audit_actions.LoginFailureReason.PASSWORD_CHANGE_CHALLENGE_INVALID

    def test_an_unknown_challenge_costs_a_password_hash_like_the_others(self, signin):
        with patch("modules.auth.credentials.password_hasher.PasswordHasher.dummy_verify") as dummy:
            _change(signin, "u" * 43)

        dummy.assert_called_once()

    def test_a_client_type_other_than_the_recorded_one_answers_alike(self, signin):
        challenge = _start(signin, WEB)
        unknown = _change(signin, "u" * 43)

        mismatched = _change(signin, challenge, headers=MOBILE)

        assert (mismatched.status_code, mismatched.json()) == (unknown.status_code, unknown.json())
        assert _credential(signin).password_change_required is True
        assert _sessions(signin) == 0

    def test_an_expired_challenge_is_refused(self, signin):
        challenge = _start(signin)
        _store().claim(challenge)

        assert _change(signin, challenge).status_code == 401

    def test_a_password_changed_in_the_meantime_voids_the_challenge(self, signin):
        challenge = _start(signin)
        with signin.factory() as db:
            credentials_integration.set_local_password_hash(
                USER_ID,
                credentials_integration.get_password_hasher().hash_password("chosen elsewhere 11"),
                db,
                change_required=False,
            )
            db.commit()

        response = _change(signin, challenge)

        assert response.status_code == 401
        assert _sessions(signin) == 0

    def test_an_account_deactivated_in_the_meantime_is_refused(self, signin):
        import modules.users.users.models as users_models

        challenge = _start(signin)
        with signin.factory() as db:
            db.get(users_models.Users, USER_ID).active = False
            db.commit()

        response = _change(signin, challenge)

        assert response.status_code == 403
        assert _credential(signin).password_change_required is True
        assert _sessions(signin) == 0

    @pytest.mark.parametrize(
        ("password", "code"),
        [
            ("tenchars!!", "password-too-short"),
            (PASSWORD, "password-unchanged"),
            ("passwordpassword", "password-too-common"),
        ],
    )
    def test_a_policy_failure_is_422_and_keeps_the_challenge(self, signin, password, code):
        challenge = _start(signin)

        response = _change(signin, challenge, password)

        assert response.status_code == 422
        assert response.json()["type"] == f"urn:endurain:error:{code}"
        assert _credential(signin).password_change_required is True
        assert _sessions(signin) == 0
        assert _change(signin, challenge).status_code == 200

    def test_losing_the_claim_writes_nothing_and_is_401(self, signin):
        challenge = _start(signin)

        with patch.object(pending_store.PendingPasswordChanges, "claim", return_value=None):
            response = _change(signin, challenge)

        assert response.status_code == 401
        credential = _credential(signin)
        assert credential.password_change_required is True
        assert credentials_integration.verify_and_update_password(
            PASSWORD, credential.password_hash, credentials_integration.get_password_hasher()
        )[0]
        assert _sessions(signin) == 0

    def test_a_store_outage_is_503(self, signin):
        with patch.object(
            pending_store.PendingPasswordChanges,
            "get",
            side_effect=pending_store.AuthSecurityStoreUnavailableError("x"),
        ):
            assert _change(signin, CHALLENGE).status_code == 503

    @pytest.mark.parametrize(
        "body",
        [
            {"password_change_challenge": "short", "password": NEW_PASSWORD},
            {"password_change_challenge": CHALLENGE},
            {"password_change_challenge": CHALLENGE, "password": NEW_PASSWORD, "extra": 1},
        ],
    )
    def test_a_malformed_request_is_422(self, signin, body):
        assert signin.client.post("/auth/password-change", json=body, headers=WEB).status_code == 422

    def test_the_client_type_header_is_required(self, signin):
        response = signin.client.post(
            "/auth/password-change", json={"password_change_challenge": CHALLENGE, "password": NEW_PASSWORD}
        )

        assert response.status_code == 422
