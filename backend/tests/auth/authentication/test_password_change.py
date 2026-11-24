"""An administrator-set password must be changed at the next sign-in, before any session exists."""

import uuid

import pytest
import sqlalchemy as sa

import core.dependencies as core_dependencies
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.step_up_store as step_up_store
import modules.auth.authentication.pending_password_change_store as pending_store
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.users.users.models as users_models
from tests._factories.tokens import audit_rows, make_reset_token
from tests._factories.users import PASSWORD
from tests.auth.authentication.conftest import (
    CHALLENGE,
    MOBILE,
    NEW_PASSWORD,
    PASSWORD_CHANGE,
    WEB,
    WRONG_CODE,
    Account,
    login,
    pending_mfa_store,
    session_count,
    verify,
)

_LOGINS = login_audit_actions.LOGIN


def _credential(sessions, account: Account):
    with sessions() as db:
        return credentials_integration.get_credential(account.user.id, db)


def _store() -> pending_store.PendingPasswordChanges:
    return pending_store.PendingPasswordChanges(core_dependencies.get_platform_state())


def _start(client, account: Account, headers=WEB) -> str:
    return login(client, account, headers).json()["password_change_challenge"]


def _change(client, challenge: str, password: str = NEW_PASSWORD, headers=WEB):
    return client.post(
        PASSWORD_CHANGE, json={"password_change_challenge": challenge, "password": password}, headers=headers
    )


def _signs_in_with(sessions, password: str, account: Account) -> bool:
    credential = _credential(sessions, account)
    return credentials_integration.verify_and_update_password(
        password, credential.password_hash, credentials_integration.get_password_hasher()
    )[0]


class TestSignInOfAFlaggedAccount:
    def test_the_right_password_answers_password_change_and_creates_no_session(
        self, client, committed_sessions, must_change_account
    ):
        response = login(client, must_change_account)

        body = response.json()
        assert response.status_code == 200
        assert body.keys() == {"next_step", "password_change_challenge"}
        assert body["next_step"] == "password_change"
        assert session_count(committed_sessions, must_change_account.user.id) == 0
        assert "set-cookie" not in response.headers
        assert response.headers["cache-control"] == "no-store"

    def test_the_challenge_names_the_login_and_the_generation_it_was_issued_under(
        self, client, committed_sessions, must_change_account
    ):
        challenge = _start(client, must_change_account)

        with committed_sessions() as db:
            generation = security_generation_integration.current_generation(must_change_account.user.id, db)
        assert _store().get(challenge) == pending_store.PendingPasswordChange(
            user_id=must_change_account.user.id,
            client_type=auth_constants.ClientType.WEB,
            code_challenge=None,
            code_challenge_method=None,
            mfa=False,
            security_generation=generation,
        )

    def test_a_mobile_login_records_the_pkce_values(self, client, must_change_account):
        record = _store().get(_start(client, must_change_account, MOBILE))

        assert record is not None
        assert record.client_type == auth_constants.ClientType.MOBILE
        assert (record.code_challenge, record.code_challenge_method) == (CHALLENGE, "S256")

    def test_the_failed_attempt_counters_are_reset_because_the_password_was_right(self, app, must_change_account):
        from tests.auth.authentication.conftest import from_address

        client = from_address(app, "203.0.113.5")
        for _ in range(4):
            login(client, must_change_account, password="wrong")

        login(client, must_change_account)

        # Four more failures stay below the five that lock a client, so the earlier four were forgotten.
        for _ in range(4):
            assert login(client, must_change_account, password="wrong").status_code == 401

    def test_an_account_that_chose_its_password_signs_in_directly(self, client, account):
        assert login(client, account).json()["next_step"] == "tokens"

    def test_with_mfa_the_step_comes_after_the_code_and_remembers_it(
        self, client, committed_sessions, mfa_must_change_account
    ):
        account = mfa_must_change_account
        challenge = login(client, account).json()["mfa_challenge"]

        response = verify(client, challenge, account.backup_code)

        assert response.json()["next_step"] == "password_change"
        record = _store().get(response.json()["password_change_challenge"])
        assert record is not None
        assert (record.user_id, record.mfa) == (account.user.id, True)
        assert session_count(committed_sessions, account.user.id) == 0

    def test_with_mfa_a_wrong_code_does_not_reveal_a_password_change(self, client, mfa_must_change_account):
        challenge = login(client, mfa_must_change_account).json()["mfa_challenge"]

        response = verify(client, challenge, WRONG_CODE)

        assert response.status_code == 400
        assert "password_change_challenge" not in response.text


class TestWhoFlagsTheAccount:
    def test_an_administrator_setting_the_password_makes_the_next_sign_in_ask_for_a_new_one(
        self, client, committed_sessions, account
    ):
        with committed_sessions() as db:
            account_security_service.change_managed_user_password(account.user.id, "set by an administrator 9", db)
            db.commit()

        assert _credential(committed_sessions, account).password_change_required is True
        response = login(client, account, password="set by an administrator 9")
        assert response.json()["next_step"] == "password_change"

    def test_the_owner_changing_the_password_clears_the_requirement(self, committed_sessions, must_change_account):
        with committed_sessions() as db:
            account_security_service.stage_change_own_password(
                must_change_account.user.id,
                must_change_account.password,
                NEW_PASSWORD,
                None,
                step_up_store.StepUpAttempts(core_dependencies.get_platform_state()),
                db,
                revoke_other_sessions=False,
                current_session_id=uuid.uuid4(),
            )
            db.commit()

        assert _credential(committed_sessions, must_change_account).password_change_required is False


class TestPasswordChangeRoute:
    def test_a_web_change_writes_the_password_clears_the_flag_signs_in_and_is_audited(
        self, client, committed_sessions, must_change_account, published
    ):
        events = published(account_security_events.ACCOUNT_SECURITY_CHANGED)
        challenge = _start(client, must_change_account)

        response = _change(client, challenge)

        body = response.json()
        assert response.status_code == 200
        assert body["next_step"] == "tokens"
        assert "csrf_token" not in body
        assert "refresh_token" not in body
        assert "refresh_token" in "".join(response.headers.get_list("set-cookie"))
        assert response.headers["cache-control"] == "no-store"
        assert _credential(committed_sessions, must_change_account).password_change_required is False
        assert _signs_in_with(committed_sessions, NEW_PASSWORD, must_change_account)
        assert session_count(committed_sessions, must_change_account.user.id) == 1
        (change,) = audit_rows(committed_sessions, account_security_audit_actions.PASSWORD_CHANGE)
        assert change.target_id == str(must_change_account.user.id)
        (row,) = audit_rows(committed_sessions, _LOGINS)
        assert (row.outcome, row.details["mfa"]) == ("success", False)
        assert [e.payload["change"] for e in events] == ["password_changed"]

    def test_the_change_voids_unused_password_reset_tokens(self, client, committed_sessions, must_change_account):
        with committed_sessions() as db:
            make_reset_token(db, must_change_account.user)
            db.commit()
        challenge = _start(client, must_change_account)

        _change(client, challenge)

        with committed_sessions() as db:
            used = db.scalars(
                sa.select(password_reset_models.PasswordResetToken.used).where(
                    password_reset_models.PasswordResetToken.user_id == must_change_account.user.id
                )
            ).all()
        assert used == [True]

    def test_the_new_password_signs_in_and_the_old_one_does_not(self, client, must_change_account):
        _change(client, _start(client, must_change_account))

        assert login(client, must_change_account, password=NEW_PASSWORD).json()["next_step"] == "tokens"
        assert login(client, must_change_account).status_code == 401

    def test_a_mobile_change_with_a_pkce_record_answers_an_exchange_session(
        self, client, committed_sessions, must_change_account
    ):
        challenge = _start(client, must_change_account, MOBILE)

        response = _change(client, challenge, headers=MOBILE)

        body = response.json()
        assert body["next_step"] == "exchange"
        assert body["session_id"]
        assert "access_token" not in body
        assert session_count(committed_sessions, must_change_account.user.id) == 1

    def test_an_mfa_login_is_audited_as_one(self, client, committed_sessions, mfa_must_change_account):
        account = mfa_must_change_account
        step = verify(client, login(client, account).json()["mfa_challenge"], account.backup_code).json()[
            "password_change_challenge"
        ]

        response = _change(client, step)

        assert response.status_code == 200
        (row,) = audit_rows(committed_sessions, _LOGINS)
        assert (row.outcome, row.details["mfa"]) == ("success", True)

    def test_the_challenge_works_once(self, client, must_change_account):
        challenge = _start(client, must_change_account)

        assert _change(client, challenge).status_code == 200
        assert _change(client, challenge, "another passphrase 77").status_code == 401

    def test_an_unknown_challenge_is_401_writes_nothing_and_is_audited(
        self, client, committed_sessions, must_change_account
    ):
        response = _change(client, "u" * 43)

        assert response.status_code == 401
        assert _credential(committed_sessions, must_change_account).password_change_required is True
        assert session_count(committed_sessions, must_change_account.user.id) == 0
        (row,) = audit_rows(committed_sessions, _LOGINS)
        assert (row.outcome, row.target_id) == ("failure", None)
        assert row.details["reason"] == login_audit_actions.LoginFailureReason.PASSWORD_CHANGE_CHALLENGE_INVALID

    def test_a_client_type_other_than_the_recorded_one_is_answered_like_an_unknown_challenge(
        self, client, committed_sessions, must_change_account
    ):
        challenge = _start(client, must_change_account, WEB)
        unknown = _change(client, "u" * 43)

        mismatched = _change(client, challenge, headers=MOBILE)

        assert (mismatched.status_code, mismatched.json()["detail"]) == (unknown.status_code, unknown.json()["detail"])
        assert _credential(committed_sessions, must_change_account).password_change_required is True
        assert session_count(committed_sessions, must_change_account.user.id) == 0

    def test_an_expired_challenge_is_refused(self, client, must_change_account):
        challenge = _start(client, must_change_account)
        _store().claim(challenge)

        assert _change(client, challenge).status_code == 401

    def test_a_password_changed_in_the_meantime_voids_the_challenge(
        self, client, committed_sessions, must_change_account
    ):
        challenge = _start(client, must_change_account)
        with committed_sessions() as db:
            credentials_integration.set_local_password_hash(
                must_change_account.user.id,
                credentials_integration.get_password_hasher().hash_password("chosen elsewhere 11"),
                db,
                change_required=False,
            )
            db.commit()

        response = _change(client, challenge)

        assert response.status_code == 401
        assert session_count(committed_sessions, must_change_account.user.id) == 0

    def test_an_account_deactivated_in_the_meantime_is_refused(self, client, committed_sessions, must_change_account):
        challenge = _start(client, must_change_account)
        with committed_sessions() as db:
            db.execute(
                sa.update(users_models.Users)
                .where(users_models.Users.id == must_change_account.user.id)
                .values(active=False)
            )
            db.commit()

        response = _change(client, challenge)

        assert response.status_code == 403
        assert _credential(committed_sessions, must_change_account).password_change_required is True
        assert session_count(committed_sessions, must_change_account.user.id) == 0

    @pytest.mark.parametrize(
        ("password", "code"),
        [
            ("tenchars!!", "password-too-short"),
            ("short", "password-too-short"),
            (PASSWORD, "password-unchanged"),
            ("passwordpassword", "password-too-common"),
        ],
    )
    def test_a_policy_failure_is_422_and_keeps_the_challenge(
        self, client, committed_sessions, must_change_account, password, code
    ):
        challenge = _start(client, must_change_account)

        response = _change(client, challenge, password)

        assert response.status_code == 422
        assert response.json()["type"] == f"urn:endurain:error:{code}"
        assert _credential(committed_sessions, must_change_account).password_change_required is True
        assert session_count(committed_sessions, must_change_account.user.id) == 0
        assert _change(client, challenge).status_code == 200

    def test_a_store_outage_is_503(self, state_outage, client):
        state_outage()

        assert _change(client, CHALLENGE).status_code == 503

    @pytest.mark.parametrize(
        "body",
        [
            {"password_change_challenge": "short", "password": NEW_PASSWORD},
            {"password_change_challenge": CHALLENGE},
            {"password_change_challenge": CHALLENGE, "password": NEW_PASSWORD, "extra": 1},
        ],
    )
    def test_a_malformed_request_is_422(self, client, body):
        assert client.post(PASSWORD_CHANGE, json=body, headers=WEB).status_code == 422

    def test_the_client_type_header_is_required(self, client):
        response = client.post(PASSWORD_CHANGE, json={"password_change_challenge": CHALLENGE, "password": NEW_PASSWORD})

        assert response.status_code == 422


class TestSecurityGeneration:
    """The challenge is redeemed only while the account's security is as it was when the challenge was issued."""

    @staticmethod
    def _assert_refused_and_nothing_created(client, sessions, account, challenge):
        assert _credential(sessions, account).password_change_required is True
        assert session_count(sessions, account.user.id) == 0
        assert _store().get(challenge) is None
        row = audit_rows(sessions, _LOGINS)[-1]
        assert row.outcome == "failure"
        assert row.details["reason"] == login_audit_actions.LoginFailureReason.SECURITY_CHANGED

    def test_an_unchanged_account_completes_the_change(self, client, committed_sessions, must_change_account):
        with committed_sessions() as db:
            security_generation_integration.stage_bump(must_change_account.user.id, db)
            db.commit()
        challenge = _start(client, must_change_account)

        assert _change(client, challenge).status_code == 200
        assert session_count(committed_sessions, must_change_account.user.id) == 1

    def test_a_security_change_after_the_challenge_refuses_it(self, client, committed_sessions, must_change_account):
        challenge = _start(client, must_change_account)
        with committed_sessions() as db:
            security_generation_integration.stage_bump(must_change_account.user.id, db)
            db.commit()

        response = _change(client, challenge)

        assert response.status_code == 401
        self._assert_refused_and_nothing_created(client, committed_sessions, must_change_account, challenge)

    def test_a_challenge_without_a_stamp_is_refused(self, client, committed_sessions, must_change_account):
        challenge = _store().add(
            pending_store.PendingPasswordChange(
                user_id=must_change_account.user.id,
                client_type=auth_constants.ClientType.WEB,
                code_challenge=None,
                code_challenge_method=None,
                mfa=False,
            )
        )

        response = _change(client, challenge)

        assert response.status_code == 401
        self._assert_refused_and_nothing_created(client, committed_sessions, must_change_account, challenge)

    def test_an_administrator_setting_the_password_after_the_challenge_refuses_it(
        self, client, committed_sessions, must_change_account
    ):
        challenge = _start(client, must_change_account)
        with committed_sessions() as db:
            account_security_service.change_managed_user_password(
                must_change_account.user.id, "set by an administrator 9", db
            )
            db.commit()

        response = _change(client, challenge)

        assert response.status_code == 401
        assert session_count(committed_sessions, must_change_account.user.id) == 0
        assert _store().get(challenge) is None

    def test_the_mfa_challenge_hands_its_generation_to_the_password_change_step(
        self, client, committed_sessions, mfa_must_change_account
    ):
        account = mfa_must_change_account
        challenge = login(client, account).json()["mfa_challenge"]
        generation = pending_mfa_store().get_pending_login(challenge).security_generation

        step = verify(client, challenge, account.backup_code).json()["password_change_challenge"]

        assert _store().get(step).security_generation == generation
