"""The MFA challenge is bound to the client network, ends after three wrong codes and answers 401 once dead."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
from jasil.backends.state_memory import MemoryState
from sqlalchemy import func, select

import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.network as core_network
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.authentication.sso_exchange_service as sso_exchange_service
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.service as sessions_service
from tests.auth.authentication.conftest import BACKUP_CODE, MOBILE, PASSWORD, USER_ID, USERNAME, WEB

_LOGIN = "auth.session.login"
_WRONG = "000000"
_SSO = "modules.auth.authentication.sso_exchange_service"


def _start(stack, headers=WEB, ip=None):
    data = {"username": USERNAME, "password": PASSWORD}
    if ip is None:
        return stack.client.post("/auth/login", data=data, headers=headers).json()["mfa_challenge"]
    with patch.object(core_network, "get_ip_address", return_value=ip):
        return stack.client.post("/auth/login", data=data, headers=headers).json()["mfa_challenge"]


def _verify(stack, challenge, code=BACKUP_CODE, headers=WEB, ip=None):
    body = {"mfa_challenge": challenge, "mfa_code": code}
    if ip is None:
        return stack.client.post("/auth/mfa/verify", json=body, headers=headers)
    with patch.object(core_network, "get_ip_address", return_value=ip):
        return stack.client.post("/auth/mfa/verify", json=body, headers=headers)


def _unused_codes(stack) -> int:
    with stack.factory() as db:
        return len(backup_codes_crud.get_user_unused_backup_codes(USER_ID, db))


def _sessions(stack) -> int:
    with stack.factory() as db:
        return db.execute(select(func.count()).select_from(sessions_models.UsersSessions)).scalar_one()


def _store() -> pending_login_store.PendingMFALogin:
    return pending_login_store.PendingMFALogin(core_dependencies.get_platform_state())


class TestSecurityGeneration:
    """The challenge is redeemed only while the account's security is as it was when the challenge was issued."""

    def _assert_refused_before_the_code(self, stack, challenge, audit, record_failed):
        entry = audit.assert_audited(_LOGIN, outcome="failure", target_type="user", target_id=str(USER_ID))
        assert entry.details["reason"] == "security_changed"
        assert entry.details["mfa"] is True
        assert _sessions(stack) == 0
        assert _unused_codes(stack) == 1
        assert _store().get_pending_login(challenge) is None
        record_failed.assert_not_called()

    def _stale_verify(self, stack, challenge, code=BACKUP_CODE):
        with (
            jasil_testing.capture_audit() as audit,
            patch.object(pending_login_store.PendingMFALogin, "record_failed_attempt") as record_failed,
            patch.object(pending_login_store.PendingMFALogin, "record_wrong_code") as record_wrong,
        ):
            response = _verify(stack, challenge, code)
        record_wrong.assert_not_called()
        return response, audit, record_failed

    def test_the_challenge_carries_the_generation_it_was_issued_under(self, mfa_plain_signin, security_generations):
        security_generations.generations[USER_ID] = 6

        assert _store().get_pending_login(_start(mfa_plain_signin)).security_generation == 6

    def test_an_unchanged_account_completes_the_sign_in(self, mfa_plain_signin, security_generations):
        security_generations.generations[USER_ID] = 6
        challenge = _start(mfa_plain_signin)

        assert _verify(mfa_plain_signin, challenge).status_code == 200
        assert _sessions(mfa_plain_signin) == 1

    def test_a_security_change_refuses_a_correct_code_before_it_is_checked(
        self, mfa_plain_signin, security_generations
    ):
        challenge = _start(mfa_plain_signin)
        security_generations.stage_bump(USER_ID, None)

        response, audit, record_failed = self._stale_verify(mfa_plain_signin, challenge)

        unknown = _verify(mfa_plain_signin, "u" * 43)
        assert (response.status_code, response.json()) == (unknown.status_code, unknown.json())
        assert response.status_code == 401
        self._assert_refused_before_the_code(mfa_plain_signin, challenge, audit, record_failed)

    def test_a_security_change_refuses_a_wrong_code_as_dead_not_as_wrong(self, mfa_plain_signin, security_generations):
        challenge = _start(mfa_plain_signin)
        security_generations.stage_bump(USER_ID, None)

        response, audit, record_failed = self._stale_verify(mfa_plain_signin, challenge, _WRONG)

        assert response.status_code == 401
        self._assert_refused_before_the_code(mfa_plain_signin, challenge, audit, record_failed)

    def test_a_challenge_without_a_stamp_is_refused(self, mfa_plain_signin):
        with patch.object(core_network, "get_ip_address", return_value="203.0.113.5"):
            challenge = _store().add_pending_login(
                pending_login_store.PendingLogin(
                    user_id=USER_ID,
                    client_type=auth_constants.ClientType.WEB,
                    code_challenge=None,
                    code_challenge_method=None,
                    client_network=core_network.client_network("203.0.113.5"),
                )
            )

        with (
            jasil_testing.capture_audit() as audit,
            patch.object(pending_login_store.PendingMFALogin, "record_failed_attempt") as record_failed,
            patch.object(core_network, "get_ip_address", return_value="203.0.113.5"),
        ):
            response = mfa_plain_signin.client.post(
                "/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": BACKUP_CODE}, headers=WEB
            )

        assert response.status_code == 401
        self._assert_refused_before_the_code(mfa_plain_signin, challenge, audit, record_failed)

    def test_an_administrator_resetting_the_mfa_after_the_challenge_refuses_it(
        self, mfa_plain_signin, security_generations
    ):
        challenge = _start(mfa_plain_signin)
        with mfa_plain_signin.factory() as db:
            account_security_service.reset_managed_user_mfa(USER_ID, db)
            db.commit()

        assert _verify(mfa_plain_signin, challenge).status_code == 401
        assert _sessions(mfa_plain_signin) == 0

    def test_the_owner_changing_the_password_after_the_challenge_refuses_it(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin)
        with (
            mfa_plain_signin.factory() as db,
            patch.object(account_security_service.step_up_service, "verify_step_up_credentials"),
        ):
            account_security_service.stage_change_own_password(
                USER_ID,
                PASSWORD,
                "a brand new passphrase 42",
                None,
                MagicMock(),
                db,
                revoke_other_sessions=False,
                current_session_id="session-1",
            )
            db.commit()

        assert _verify(mfa_plain_signin, challenge).status_code == 401
        assert _sessions(mfa_plain_signin) == 0

    def test_signing_out_everywhere_after_the_challenge_refuses_it(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin)
        with mfa_plain_signin.factory() as db:
            sessions_service.delete_sessions_by_user_and_commit(USER_ID, MagicMock(), lambda step_up: None, db)

        assert _verify(mfa_plain_signin, challenge).status_code == 401
        assert _sessions(mfa_plain_signin) == 0


class TestNetworkBinding:
    def test_a_challenge_presented_from_another_network_is_a_401_audited_against_the_user(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin, ip="203.0.113.5")

        with jasil_testing.capture_audit() as audit:
            response = _verify(mfa_plain_signin, challenge, ip="198.51.100.9")

        assert response.status_code == 401
        entry = audit.assert_audited(_LOGIN, outcome="failure", target_type="user", target_id=str(USER_ID))
        assert entry.details == {
            "method": "password",
            "mfa": True,
            "reason": "mfa_challenge_network_mismatch",
            "new_device": False,
        }
        assert _unused_codes(mfa_plain_signin) == 1

    def test_the_challenge_still_works_from_the_network_of_the_password_step(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin, ip="203.0.113.5")
        _verify(mfa_plain_signin, challenge, ip="198.51.100.9")

        assert _verify(mfa_plain_signin, challenge, ip="203.0.113.5").status_code == 200

    def test_another_address_of_the_same_ipv6_64_is_the_same_network(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin, ip="2001:db8:1:2::1")

        assert _verify(mfa_plain_signin, challenge, ip="2001:db8:1:2:aaaa::7").status_code == 200

    def test_another_ipv6_64_is_another_network(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin, ip="2001:db8:1:2::1")

        assert _verify(mfa_plain_signin, challenge, ip="2001:db8:1:3::1").status_code == 401


class TestDeadChallengeAnswers401:
    def test_an_unknown_challenge_is_401_and_costs_no_password_hash(self, mfa_plain_signin):
        with patch("modules.auth.credentials.password_hasher.PasswordHasher.dummy_verify") as dummy:
            response = _verify(mfa_plain_signin, "u" * 43)

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        dummy.assert_not_called()

    def test_a_challenge_of_the_other_client_type_is_401(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin, WEB)

        assert _verify(mfa_plain_signin, challenge, headers=MOBILE).status_code == 401

    def test_a_wrong_code_on_a_live_challenge_stays_400(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin)

        assert _verify(mfa_plain_signin, challenge, _WRONG).status_code == 400

    def test_a_lost_claim_is_401(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin)

        with patch.object(pending_login_store.PendingMFALogin, "claim_pending_login", return_value=None):
            assert _verify(mfa_plain_signin, challenge).status_code == 401


class TestAttemptCap:
    def test_the_third_wrong_code_ends_the_challenge(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin)

        statuses = [_verify(mfa_plain_signin, challenge, _WRONG).status_code for _ in range(3)]

        assert statuses == [400, 400, 401]
        assert _verify(mfa_plain_signin, challenge).status_code == 401
        assert _unused_codes(mfa_plain_signin) == 1

    def test_two_wrong_codes_leave_the_challenge_usable(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin)
        for _ in range(2):
            _verify(mfa_plain_signin, challenge, _WRONG)

        assert _verify(mfa_plain_signin, challenge).status_code == 200

    def test_each_challenge_counts_its_own_wrong_codes(self, mfa_plain_signin):
        first, second = _start(mfa_plain_signin), _start(mfa_plain_signin)
        for _ in range(2):
            _verify(mfa_plain_signin, first, _WRONG)

        assert _verify(mfa_plain_signin, second, _WRONG).status_code == 400


class TestBackupCodeCommitOrder:
    def test_a_backup_code_stays_unused_when_the_challenge_claim_is_lost(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin)

        with patch.object(pending_login_store.PendingMFALogin, "claim_pending_login", return_value=None):
            assert _verify(mfa_plain_signin, challenge).status_code == 401

        assert _unused_codes(mfa_plain_signin) == 1

    def test_a_backup_code_is_consumed_by_the_sign_in_it_completes(self, mfa_plain_signin):
        challenge = _start(mfa_plain_signin)

        assert _verify(mfa_plain_signin, challenge).status_code == 200

        assert _unused_codes(mfa_plain_signin) == 0

    def test_a_backup_code_is_consumed_when_a_password_change_step_follows(self, mfa_signin):
        challenge = _start(mfa_signin)

        assert _verify(mfa_signin, challenge).json()["next_step"] == "password_change"

        assert _unused_codes(mfa_signin) == 0


def _exchange(stack, *, claimed: bool):
    """Run the SSO token exchange for the account with MFA, committing only what the service commits."""
    oauth_state = SimpleNamespace(
        id="state",
        purpose="login",
        code_challenge="c",
        code_challenge_method="S256",
        client_type="web",
        idp_id=3,
        security_generation=0,
    )
    session = SimpleNamespace(
        user_id=USER_ID, tokens_exchanged=False, expires_at=datetime(2999, 1, 1, tzinfo=UTC), client_type="web"
    )
    tokens = ("sid", datetime(2999, 1, 1, tzinfo=UTC), "at", datetime(2999, 1, 1, tzinfo=UTC), "rt", "csrf")
    with (
        patch(f"{_SSO}.sessions_integration.get_session_with_oauth_state", return_value=(session, oauth_state)),
        patch(f"{_SSO}.auth_computation.validate_pkce_verifier"),
        patch(f"{_SSO}.server_settings_integration.get_session_policy"),
        patch(f"{_SSO}.authentication_token_service.create_tokens", return_value=tokens),
        patch(
            f"{_SSO}.sessions_integration.claim_session_for_token_exchange",
            return_value=datetime(2999, 1, 1, tzinfo=UTC) if claimed else None,
        ),
        patch(f"{_SSO}.known_devices_integration.record_sign_in", return_value=MagicMock(new_device=False)),
        patch(f"{_SSO}.authentication_token_service.build_web_token_response"),
        stack.factory() as db,
    ):
        try:
            sso_exchange_service.exchange_tokens_for_session(
                "sid",
                "verifier",
                BACKUP_CODE,
                "web",
                "127.0.0.1",
                "agent",
                pending_login_store.PendingMFALogin(MemoryState()),
                credentials_integration.get_password_hasher(),
                MagicMock(),
                db,
                device_id=None,
            )
        except core_exceptions.DomainError as err:
            return err
    return None


class TestSsoExchangeCommitOrder:
    def test_a_backup_code_stays_unused_when_the_exchange_claim_is_lost(self, mfa_plain_signin):
        err = _exchange(mfa_plain_signin, claimed=False)

        assert isinstance(err, core_exceptions.ConflictError)
        assert _unused_codes(mfa_plain_signin) == 1

    def test_a_backup_code_is_consumed_by_the_exchange_it_completes(self, mfa_plain_signin):
        assert _exchange(mfa_plain_signin, claimed=True) is None

        assert _unused_codes(mfa_plain_signin) == 0
