"""An account with MFA signs in with a challenge: bound to its client, ended by three wrong codes, 401 once dead."""

import pytest
import sqlalchemy as sa

import core.network as core_network
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.constants as auth_constants
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.users.users.models as users_models
from tests._factories.tokens import audit_rows, totp_code
from tests.auth.authentication.conftest import (
    MOBILE,
    WEB,
    WRONG_CODE,
    exchange,
    from_address,
    login,
    pending_mfa_store,
    session_count,
    verify,
)


def _challenge(client, account, headers=WEB) -> str:
    return login(client, account, headers).json()["mfa_challenge"]


def _unused_codes(sessions, account) -> int:
    with sessions() as db:
        return len(backup_codes_crud.get_user_unused_backup_codes(account.user.id, db))


def _logins(sessions):
    return audit_rows(sessions, login_audit_actions.LOGIN)


def _bump_security(sessions, account) -> None:
    with sessions() as db:
        security_generation_integration.stage_bump(account.user.id, db)
        db.commit()


class TestPasswordStep:
    def test_the_answer_is_a_challenge_and_the_kinds_of_code_the_account_can_answer_with(self, client, mfa_account):
        body = login(client, mfa_account).json()

        assert body["next_step"] == "mfa"
        assert body["methods"] == ["totp", "backup_code"]
        assert set(body) == {"next_step", "mfa_challenge", "methods"}

    def test_the_password_step_creates_no_session_and_writes_no_success_row(
        self, client, committed_sessions, mfa_account
    ):
        login(client, mfa_account)

        assert session_count(committed_sessions, mfa_account.user.id) == 0
        assert _logins(committed_sessions) == []

    def test_the_challenge_records_the_client_type_network_and_security_generation(
        self, app, committed_sessions, mfa_account
    ):
        challenge = _challenge(from_address(app, "203.0.113.5"), mfa_account, MOBILE)
        with committed_sessions() as db:
            generation = security_generation_integration.current_generation(mfa_account.user.id, db)

        pending = pending_mfa_store().get_pending_login(challenge)

        assert pending is not None
        assert pending.user_id == mfa_account.user.id
        assert pending.client_type == auth_constants.ClientType.MOBILE
        assert pending.client_network == core_network.client_network("203.0.113.5")
        assert pending.security_generation == generation

    def test_starting_a_challenge_does_not_lift_the_lockout_the_failed_passwords_built_up(self, app, mfa_account):
        client = from_address(app, "203.0.113.5")
        for _ in range(4):
            login(client, mfa_account, password="wrong")
        _challenge(client, mfa_account)

        assert login(client, mfa_account, password="wrong").status_code == 401

        assert login(client, mfa_account).status_code == 429

    def test_a_wrong_password_never_starts_a_challenge(self, client, mfa_account):
        response = login(client, mfa_account, password="not the password")

        assert response.status_code == 401
        assert "mfa_challenge" not in response.text


class TestCompletion:
    def test_a_backup_code_completes_the_sign_in_and_is_consumed_by_it(self, client, committed_sessions, mfa_account):
        challenge = _challenge(client, mfa_account)

        response = verify(client, challenge, mfa_account.backup_code)

        assert response.status_code == 200
        assert response.json()["next_step"] == "tokens"
        assert "endurain_refresh_token" in response.headers["set-cookie"]
        assert session_count(committed_sessions, mfa_account.user.id) == 1
        assert _unused_codes(committed_sessions, mfa_account) == 9

    def test_a_totp_code_completes_the_sign_in_and_leaves_the_backup_codes(
        self, client, committed_sessions, mfa_account
    ):
        challenge = _challenge(client, mfa_account)

        response = verify(client, challenge, totp_code(mfa_account.mfa.secret, steps_ahead=1))

        assert response.status_code == 200
        assert _unused_codes(committed_sessions, mfa_account) == 10

    def test_the_sign_in_is_audited_with_the_second_factor(self, client, committed_sessions, mfa_account):
        verify(client, _challenge(client, mfa_account), mfa_account.backup_code)

        (row,) = _logins(committed_sessions)
        assert (row.outcome, row.target_id) == ("success", str(mfa_account.user.id))
        assert row.details["mfa"] is True

    def test_a_challenge_completes_one_sign_in(self, client, committed_sessions, mfa_account):
        challenge = _challenge(client, mfa_account)
        verify(client, challenge, mfa_account.mfa.backup_codes[0])

        again = verify(client, challenge, mfa_account.mfa.backup_codes[1])

        assert again.status_code == 401
        assert session_count(committed_sessions, mfa_account.user.id) == 1

    def test_the_issued_tokens_are_accepted_by_a_protected_route(self, client, mfa_account):
        token = verify(client, _challenge(client, mfa_account), mfa_account.backup_code).json()["access_token"]

        profile = client.get("/api/v1/profile", headers={**WEB, "Authorization": f"Bearer {token}"})

        assert profile.status_code == 200

    def test_a_mobile_sign_in_continues_to_the_exchange_with_the_challenge_of_the_password_step(
        self, client, mfa_account
    ):
        challenge = _challenge(client, mfa_account, MOBILE)

        body = verify(client, challenge, mfa_account.backup_code, MOBILE).json()

        assert body["next_step"] == "exchange"
        assert exchange(client, body["session_id"]).json()["next_step"] == "tokens"

    def test_the_step_takes_no_pkce_parameters(self, client):
        operation = client.app.openapi()["paths"]["/api/v1/auth/mfa/verify"]["post"]

        assert {p["name"] for p in operation["parameters"]} <= {"X-Client-Type", "X-Device-Id"}

    def test_a_password_that_an_administrator_set_is_changed_after_the_code(
        self, client, committed_sessions, mfa_must_change_account
    ):
        account = mfa_must_change_account
        challenge = _challenge(client, account)

        body = verify(client, challenge, account.backup_code).json()

        assert body["next_step"] == "password_change"
        assert session_count(committed_sessions, account.user.id) == 0
        assert _unused_codes(committed_sessions, account) == 9


class TestWrongCodes:
    def test_a_wrong_code_on_a_live_challenge_is_a_400_audited_against_the_user(
        self, client, committed_sessions, mfa_account
    ):
        challenge = _challenge(client, mfa_account)

        response = verify(client, challenge, WRONG_CODE)

        assert response.status_code == 400
        (row,) = _logins(committed_sessions)
        assert (row.outcome, row.target_id) == ("failure", str(mfa_account.user.id))
        assert row.details["reason"] == "invalid_mfa_code"
        assert row.details["mfa"] is True
        assert session_count(committed_sessions, mfa_account.user.id) == 0

    def test_the_third_wrong_code_ends_the_challenge(self, client, committed_sessions, mfa_account):
        challenge = _challenge(client, mfa_account)

        statuses = [verify(client, challenge, WRONG_CODE).status_code for _ in range(3)]

        assert statuses == [400, 400, 401]
        assert verify(client, challenge, mfa_account.backup_code).status_code == 401
        assert _unused_codes(committed_sessions, mfa_account) == 10

    def test_two_wrong_codes_leave_the_challenge_usable(self, client, mfa_account):
        challenge = _challenge(client, mfa_account)
        for _ in range(2):
            verify(client, challenge, WRONG_CODE)

        assert verify(client, challenge, mfa_account.backup_code).status_code == 200

    def test_each_challenge_counts_its_own_wrong_codes(self, client, mfa_account):
        first, second = _challenge(client, mfa_account), _challenge(client, mfa_account)
        for _ in range(2):
            verify(client, first, WRONG_CODE)

        assert verify(client, second, WRONG_CODE).status_code == 400

    def test_a_backup_code_used_before_is_refused_like_a_wrong_code(self, client, mfa_account):
        verify(client, _challenge(client, mfa_account), mfa_account.backup_code)

        response = verify(client, _challenge(client, mfa_account), mfa_account.backup_code)

        assert response.status_code == 400


class TestDeadChallenge:
    def test_an_unknown_challenge_is_a_401_that_asks_for_a_new_sign_in(self, client, committed_sessions, mfa_account):
        response = verify(client, "u" * 43, mfa_account.backup_code)

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Session"
        (row,) = _logins(committed_sessions)
        assert (row.outcome, row.target_id) == ("failure", None)
        assert row.details["reason"] == "mfa_challenge_expired"

    @pytest.mark.parametrize(("started", "verified"), [(WEB, MOBILE), (MOBILE, WEB)])
    def test_a_challenge_used_by_the_other_client_type_is_refused_like_an_unknown_one(
        self, client, mfa_account, started, verified
    ):
        challenge = _challenge(client, mfa_account, started)

        wrong_kind = verify(client, challenge, mfa_account.backup_code, verified)
        unknown = verify(client, "x" * 43, mfa_account.backup_code, verified)

        assert wrong_kind.status_code == unknown.status_code == 401
        assert wrong_kind.json()["detail"] == unknown.json()["detail"]

    def test_a_challenge_refused_for_the_other_client_type_stays_usable_by_its_own_client(self, client, mfa_account):
        challenge = _challenge(client, mfa_account, MOBILE)
        verify(client, challenge, mfa_account.backup_code, WEB)

        assert verify(client, challenge, mfa_account.backup_code, MOBILE).json()["next_step"] == "exchange"


class TestNetworkBinding:
    def test_a_challenge_presented_from_another_network_is_a_401_audited_against_the_user(
        self, app, committed_sessions, mfa_account
    ):
        challenge = _challenge(from_address(app, "203.0.113.5"), mfa_account)

        response = verify(from_address(app, "198.51.100.9"), challenge, mfa_account.backup_code)

        assert response.status_code == 401
        (row,) = _logins(committed_sessions)
        assert (row.outcome, row.target_id) == ("failure", str(mfa_account.user.id))
        assert row.details == {
            "method": "password",
            "mfa": True,
            "reason": "mfa_challenge_network_mismatch",
            "new_device": False,
        }
        assert _unused_codes(committed_sessions, mfa_account) == 10

    def test_the_challenge_still_works_from_the_network_of_the_password_step(self, app, mfa_account):
        challenge = _challenge(from_address(app, "203.0.113.5"), mfa_account)
        verify(from_address(app, "198.51.100.9"), challenge, mfa_account.backup_code)

        assert verify(from_address(app, "203.0.113.5"), challenge, mfa_account.backup_code).status_code == 200

    def test_another_address_of_the_same_ipv6_64_is_the_same_network(self, app, mfa_account):
        challenge = _challenge(from_address(app, "2001:db8:1:2::1"), mfa_account)

        response = verify(from_address(app, "2001:db8:1:2:aaaa::7"), challenge, mfa_account.backup_code)

        assert response.status_code == 200

    def test_another_ipv6_64_is_another_network(self, app, mfa_account):
        challenge = _challenge(from_address(app, "2001:db8:1:2::1"), mfa_account)

        response = verify(from_address(app, "2001:db8:1:3::1"), challenge, mfa_account.backup_code)

        assert response.status_code == 401


class TestSecurityGeneration:
    """The challenge is redeemed only while the account's security is as it was when it was issued."""

    def _assert_refused_before_the_code(self, client, sessions, account, challenge) -> None:
        row = _logins(sessions)[-1]
        assert (row.outcome, row.target_id) == ("failure", str(account.user.id))
        assert row.details["reason"] == "security_changed"
        assert row.details["mfa"] is True
        assert session_count(sessions, account.user.id) == 0
        assert _unused_codes(sessions, account) == 10
        assert pending_mfa_store().get_pending_login(challenge) is None

    def test_an_unchanged_account_completes_the_sign_in(self, client, committed_sessions, mfa_account):
        _bump_security(committed_sessions, mfa_account)
        challenge = _challenge(client, mfa_account)

        assert verify(client, challenge, mfa_account.backup_code).status_code == 200

    def test_a_security_change_refuses_a_correct_code_before_it_is_checked_and_ends_the_challenge(
        self, client, committed_sessions, mfa_account
    ):
        challenge = _challenge(client, mfa_account)
        _bump_security(committed_sessions, mfa_account)

        response = verify(client, challenge, mfa_account.backup_code)

        assert response.status_code == 401
        self._assert_refused_before_the_code(client, committed_sessions, mfa_account, challenge)
        unknown = verify(client, "u" * 43, mfa_account.backup_code)
        assert (response.status_code, response.json()["detail"]) == (unknown.status_code, unknown.json()["detail"])

    def test_a_security_change_refuses_a_wrong_code_as_dead_and_counts_nothing_against_the_account(
        self, client, committed_sessions, mfa_account
    ):
        challenge = _challenge(client, mfa_account)
        _bump_security(committed_sessions, mfa_account)

        response = verify(client, challenge, WRONG_CODE)

        assert response.status_code == 401
        self._assert_refused_before_the_code(client, committed_sessions, mfa_account, challenge)
        assert not pending_mfa_store().is_locked_out(mfa_account.username, "testclient", user_id=mfa_account.user.id)

    def test_a_challenge_without_a_stamp_is_refused(self, client, committed_sessions, mfa_account):
        challenge = pending_mfa_store().add_pending_login(
            pending_login_store.PendingLogin(
                user_id=mfa_account.user.id,
                client_type=auth_constants.ClientType.WEB,
                code_challenge=None,
                code_challenge_method=None,
                client_network=core_network.client_network("testclient"),
            )
        )

        response = verify(client, challenge, mfa_account.backup_code)

        assert response.status_code == 401
        self._assert_refused_before_the_code(client, committed_sessions, mfa_account, challenge)

    def test_an_administrator_resetting_the_mfa_after_the_challenge_refuses_it(
        self, client, committed_sessions, mfa_account
    ):
        challenge = _challenge(client, mfa_account)
        with committed_sessions() as db:
            account_security_service.reset_managed_user_mfa(mfa_account.user.id, db)
            db.commit()

        assert verify(client, challenge, mfa_account.backup_code).status_code == 401
        assert session_count(committed_sessions, mfa_account.user.id) == 0

    def test_a_user_deleted_after_the_challenge_ends_the_sign_in(self, client, committed_sessions, mfa_account):
        challenge = _challenge(client, mfa_account)
        with committed_sessions() as db:
            db.execute(sa.delete(users_models.Users).where(users_models.Users.id == mfa_account.user.id))
            db.commit()

        assert verify(client, challenge, mfa_account.backup_code).status_code == 401


class TestInactiveAccount:
    def test_an_account_deactivated_after_the_password_step_is_refused_with_its_code_unspent(
        self, client, committed_sessions, mfa_account
    ):
        challenge = _challenge(client, mfa_account)
        _deactivate(committed_sessions, mfa_account)

        response = verify(client, challenge, mfa_account.backup_code)

        assert response.status_code == 403
        assert session_count(committed_sessions, mfa_account.user.id) == 0
        assert _unused_codes(committed_sessions, mfa_account) == 10


def _deactivate(sessions, account) -> None:
    with sessions() as db:
        db.execute(sa.update(users_models.Users).where(users_models.Users.id == account.user.id).values(active=False))
        db.commit()
