"""An account locked by 100 failed codes or passwords in a row still admits its known devices, and tells its owner."""

import secrets
import uuid

import sqlalchemy as sa
from jasil.backends.state_memory import MemoryState

import core.dependencies as core_dependencies
import core.hashing as core_hashing
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.authentication.events as authentication_events
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.integration_service as authentication_integration
import modules.auth.lockout.audit_actions as lockout_audit_actions
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.mfa.integration_service as mfa_integration
import modules.users.users.models as users_models
from tests._factories.devices import make_known_device
from tests._factories.tokens import audit_rows
from tests.auth.authentication.conftest import (
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

_IP = "testclient"
_LOCK = lockout_audit_actions.LOCKOUT_APPLY
_LOGINS = login_audit_actions.LOGIN


def _login_store() -> failed_login_store.FailedLoginAttempts:
    return failed_login_store.FailedLoginAttempts(core_dependencies.get_platform_state())


def _fail_logins(username: str, count: int, user_id=None) -> None:
    """Count wrong passwords against an account from as many addresses, so no client network is locked."""
    store = _login_store()
    for i in range(count):
        store.record_failed_attempt(username, f"198.51.{i // 250}.{i % 250 + 1}", user_id=user_id)


def _fail_codes(account, count: int) -> None:
    """Count wrong MFA codes against the account from as many addresses, so no client network is locked."""
    store = pending_mfa_store()
    for i in range(count):
        store.record_failed_attempt(account.username, f"198.51.{i // 250}.{i % 250 + 1}", user_id=account.user.id)


def _lock_login(account) -> None:
    _fail_logins(account.username, 100, account.user.id)


def _lock_mfa(account) -> None:
    _fail_codes(account, lockout_contracts.ACCOUNT_MFA_LOCKOUT_TIERS[0][0])


def _known_device(sessions, account) -> dict[str, str]:
    """Record a device the account signed in from, and return the header a client sends to present it."""
    device_id = secrets.token_urlsafe(32)
    with sessions() as db:
        make_known_device(db, account.user.id, core_hashing.sha256_hex(device_id))
        db.commit()
    return {"X-Device-Id": device_id}


def _locks(sessions, counter: str) -> list:
    return [r for r in audit_rows(sessions, _LOCK) if r.details["counter"] == counter]


def _start_mfa(client, account, headers=WEB) -> str:
    return login(client, account, headers).json()["mfa_challenge"]


class TestLoginLock:
    def test_an_unknown_device_is_refused_even_with_the_right_password(self, client, committed_sessions, account):
        _lock_login(account)

        response = login(client, account)

        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0
        assert session_count(committed_sessions, account.user.id) == 0
        row = audit_rows(committed_sessions, _LOGINS)[-1]
        assert (row.outcome, row.details["reason"]) == ("denied", "locked_out")

    def test_a_client_that_sends_no_device_id_is_refused(self, client, account):
        _lock_login(account)

        assert login(client, account, headers=WEB).status_code == 429

    def test_a_device_the_account_never_used_is_refused(self, client, account):
        _lock_login(account)

        response = client.post(
            "/api/v1/auth/login",
            data={"username": account.username, "password": account.password},
            headers={**WEB, "X-Device-Id": secrets.token_urlsafe(32)},
        )

        assert response.status_code == 429

    def test_a_known_device_signs_in_and_lifts_the_lock(self, client, committed_sessions, account):
        _lock_login(account)
        device = _known_device(committed_sessions, account)

        response = client.post(
            "/api/v1/auth/login",
            data={"username": account.username, "password": account.password},
            headers={**WEB, **device},
        )

        assert response.status_code == 200
        assert not _login_store().is_locked_out(account.username, _IP, user_id=account.user.id)
        assert login(client, account).status_code == 200

    def test_a_known_device_is_still_held_by_the_lock_of_its_client_network(self, app, committed_sessions, account):
        _lock_login(account)
        device = _known_device(committed_sessions, account)
        client = from_address(app, "203.0.113.5")
        for _ in range(5):
            client.post(
                "/api/v1/auth/login",
                data={"username": account.username, "password": "wrong"},
                headers={**WEB, **device},
            )

        response = client.post(
            "/api/v1/auth/login",
            data={"username": account.username, "password": account.password},
            headers={**WEB, **device},
        )

        assert response.status_code == 429

    def test_a_known_device_with_the_wrong_password_is_refused_like_any_other(
        self, client, committed_sessions, account
    ):
        _lock_login(account)
        device = _known_device(committed_sessions, account)

        response = client.post(
            "/api/v1/auth/login", data={"username": account.username, "password": "wrong"}, headers={**WEB, **device}
        )

        assert response.status_code == 401

    def test_an_unknown_username_is_locked_after_100_failures_like_an_account(self, client, account):
        _fail_logins("ghost", 100)

        response = client.post("/api/v1/auth/login", data={"username": "ghost", "password": "x"}, headers=WEB)

        assert response.status_code == 429

    def test_a_sign_in_under_a_new_username_is_refused_while_the_account_is_locked(
        self, client, committed_sessions, account
    ):
        _lock_login(account)
        with committed_sessions() as db:
            db.execute(
                sa.update(users_models.Users)
                .where(users_models.Users.id == account.user.id)
                .values(username="renamed-account")
            )
            db.commit()

        response = client.post(
            "/api/v1/auth/login", data={"username": "renamed-account", "password": account.password}, headers=WEB
        )

        assert response.status_code == 429


class TestLoginLockNotice:
    def test_the_failure_that_reaches_100_tells_the_owner_once_and_audits_it(
        self, client, committed_sessions, account, published
    ):
        events = published(authentication_events.ACCOUNT_LOCKED)
        _fail_logins(account.username, 99, account.user.id)

        response = login(client, account, password="wrong")

        assert response.status_code == 401
        assert [e.payload for e in events] == [{"user_id": str(account.user.id)}]
        (row,) = _locks(committed_sessions, "login_account")
        assert row.details == {"counter": "login_account", "failed_attempts": 100}
        assert (row.outcome, row.target_id, row.target_owner_id) == (
            "success",
            str(account.user.id),
            str(account.user.id),
        )
        assert account.username not in repr(row)

    def test_a_failure_below_100_tells_nobody(self, client, committed_sessions, account, published):
        events = published(authentication_events.ACCOUNT_LOCKED)
        _fail_logins(account.username, 98, account.user.id)

        login(client, account, password="wrong")

        assert events == []
        assert _locks(committed_sessions, "login_account") == []

    def test_a_username_that_matches_no_user_tells_nobody(self, client, committed_sessions, account, published):
        events = published(authentication_events.ACCOUNT_LOCKED)
        _fail_logins("ghost", 99)

        client.post("/api/v1/auth/login", data={"username": "ghost", "password": "x"}, headers=WEB)

        assert events == []
        assert _locks(committed_sessions, "login_account") == []

    def test_a_known_device_failing_while_locked_does_not_tell_again(
        self, client, committed_sessions, account, published
    ):
        _lock_login(account)
        device = _known_device(committed_sessions, account)
        events = published(authentication_events.ACCOUNT_LOCKED)

        client.post(
            "/api/v1/auth/login", data={"username": account.username, "password": "wrong"}, headers={**WEB, **device}
        )

        assert events == []
        assert _locks(committed_sessions, "login_account") == []


class TestLoginCounters:
    def test_the_lock_follows_the_user_id_across_a_username_change(self):
        user_id = uuid.uuid4()
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for i in range(100):
            store.record_failed_attempt("alice", f"198.51.100.{i}", user_id=user_id)

        assert store.is_locked_out("alicia", "192.0.2.1", user_id=user_id) is True
        assert store.is_locked_out("alicia", "192.0.2.1", user_id=user_id, known_device=True) is False
        assert store.record_failed_attempt("alicia", "192.0.2.1", user_id=user_id).account_locked_now is False

    def test_the_failures_before_and_after_a_rename_count_together(self):
        user_id = uuid.uuid4()
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for i in range(50):
            store.record_failed_attempt("alice", f"198.51.100.{i}", user_id=user_id)
        records = [store.record_failed_attempt("alicia", f"198.51.101.{i}", user_id=user_id) for i in range(50)]

        assert [r.account_locked_now for r in records] == [False] * 49 + [True]

    def test_an_unknown_username_locks_regardless_of_case_and_never_locks_an_account_whose_id_spells_it(self):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        records = [store.record_failed_attempt("ghost", f"198.51.100.{i}", user_id=None) for i in range(100)]

        assert [r.account_locked_now for r in records] == [False] * 99 + [True]
        assert store.is_locked_out("Ghost", _IP, user_id=None) is True
        assert store.is_locked_out("ghost", _IP, user_id=None, known_device=True) is False
        assert store.is_locked_out("ghost", _IP, user_id=uuid.uuid4()) is False

    def test_a_percent_encoded_variant_of_a_locked_unknown_username_is_not_locked(self):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for i in range(100):
            store.record_failed_attempt("ghost", f"198.51.100.{i}", user_id=None)

        assert store.is_locked_out("%67host", _IP, user_id=None) is False

    def test_clear_all_clears_the_unknown_username_counters(self):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for i in range(100):
            store.record_failed_attempt("ghost", f"198.51.100.{i}", user_id=None)

        store.clear_all()

        assert store.is_locked_out("ghost", _IP, user_id=None) is False

    def test_clearing_an_account_lock_frees_it_under_any_username_and_its_count(self, account):
        _lock_login(account)

        authentication_integration.clear_account_login_lockout(account.user.id)

        store = _login_store()
        assert store.is_locked_out("another-name", _IP, user_id=account.user.id) is False
        assert store.record_failed_attempt(account.username, _IP, user_id=account.user.id).account_locked_now is False

    def test_a_state_outage_does_not_fail_the_credential_change(self, state_outage, account):
        state_outage()

        authentication_integration.clear_account_login_lockout(account.user.id)

    def test_a_state_outage_answers_503_at_sign_in(self, state_outage, client, account):
        state_outage()

        assert login(client, account).status_code == 503


class TestTieredMfaLockIsPerNetwork:
    def test_wrong_codes_from_one_network_do_not_stop_a_correct_code_from_another(self, app, mfa_account):
        near = from_address(app, "203.0.113.5")
        for _ in range(5):
            assert verify(near, _start_mfa(near, mfa_account), WRONG_CODE).status_code == 400
        assert verify(near, _start_mfa(near, mfa_account), mfa_account.backup_code).status_code == 429

        far = from_address(app, "198.51.100.9")
        assert verify(far, _start_mfa(far, mfa_account), mfa_account.backup_code).status_code == 200

    def test_the_account_wide_lock_holds_across_networks(self, app, mfa_account):
        _lock_mfa(mfa_account)
        client = from_address(app, "198.51.100.9")

        assert verify(client, _start_mfa(client, mfa_account), mfa_account.backup_code).status_code == 429


class TestHundredthWrongCode:
    def test_it_locks_audits_once_and_tells_the_owner_once(self, client, committed_sessions, mfa_account, published):
        events = published(authentication_events.MFA_LOCKED)
        _fail_codes(mfa_account, 99)

        response = verify(client, _start_mfa(client, mfa_account), WRONG_CODE)

        assert response.status_code == 400
        (row,) = _locks(committed_sessions, "mfa_account")
        assert row.details == {"counter": "mfa_account", "failed_attempts": 100}
        assert (row.outcome, row.target_type, row.target_id, row.target_owner_id) == (
            "success",
            "user",
            str(mfa_account.user.id),
            str(mfa_account.user.id),
        )
        assert mfa_account.username not in repr(row)
        assert [e.payload for e in events] == [{"user_id": str(mfa_account.user.id)}]
        assert pending_mfa_store().is_locked_out(mfa_account.username, _IP, user_id=mfa_account.user.id)

    def test_the_ninety_ninth_wrong_code_locks_nothing_and_tells_nobody(
        self, client, committed_sessions, mfa_account, published
    ):
        events = published(authentication_events.MFA_LOCKED)
        _fail_codes(mfa_account, 98)

        response = verify(client, _start_mfa(client, mfa_account), WRONG_CODE)

        assert response.status_code == 400
        assert _locks(committed_sessions, "mfa_account") == []
        assert events == []
        assert not pending_mfa_store().is_locked_out(mfa_account.username, _IP, user_id=mfa_account.user.id)

    def test_a_known_device_that_gets_the_code_wrong_still_counts_toward_the_cap(
        self, client, committed_sessions, mfa_account, published
    ):
        events = published(authentication_events.MFA_LOCKED)
        _fail_codes(mfa_account, 99)
        device = _known_device(committed_sessions, mfa_account)

        response = verify(client, _start_mfa(client, mfa_account), WRONG_CODE, {**WEB, **device})

        assert response.status_code == 400
        assert len(events) == 1

    def test_a_wrong_code_while_locked_does_not_tell_again(self, client, committed_sessions, mfa_account, published):
        _lock_mfa(mfa_account)
        device = _known_device(committed_sessions, mfa_account)
        events = published(authentication_events.MFA_LOCKED)

        response = verify(client, _start_mfa(client, mfa_account, {**WEB, **device}), WRONG_CODE, {**WEB, **device})

        assert response.status_code == 400
        assert events == []
        assert _locks(committed_sessions, "mfa_account") == []


class TestLockedMfaAccount:
    def test_an_unknown_device_is_refused_even_with_a_correct_code(self, client, committed_sessions, mfa_account):
        _lock_mfa(mfa_account)

        response = verify(client, _start_mfa(client, mfa_account), mfa_account.backup_code)

        assert response.status_code == 429
        row = audit_rows(committed_sessions, _LOGINS)[-1]
        assert (row.outcome, row.target_id) == ("denied", str(mfa_account.user.id))
        assert (row.details["reason"], row.details["mfa"]) == ("locked_out", True)
        assert session_count(committed_sessions, mfa_account.user.id) == 0

    def test_a_known_device_completes_with_a_correct_code_and_lifts_the_lock(
        self, client, committed_sessions, mfa_account
    ):
        _lock_mfa(mfa_account)
        device = _known_device(committed_sessions, mfa_account)

        response = verify(client, _start_mfa(client, mfa_account), mfa_account.backup_code, {**WEB, **device})

        assert response.status_code == 200
        assert not pending_mfa_store().is_locked_out(mfa_account.username, _IP, user_id=mfa_account.user.id)

    def test_a_known_device_is_still_held_by_the_tiered_lock(self, app, committed_sessions, mfa_account):
        _lock_mfa(mfa_account)
        device = _known_device(committed_sessions, mfa_account)
        client = from_address(app, "203.0.113.5")
        for _ in range(5):
            verify(client, _start_mfa(client, mfa_account), WRONG_CODE, {**WEB, **device})

        response = verify(client, _start_mfa(client, mfa_account), mfa_account.backup_code, {**WEB, **device})

        assert response.status_code == 429

    def test_a_success_forgets_the_account_count(self, client, mfa_account, published):
        events = published(authentication_events.MFA_LOCKED)
        _fail_codes(mfa_account, 99)
        assert verify(client, _start_mfa(client, mfa_account), mfa_account.backup_code).status_code == 200

        assert verify(client, _start_mfa(client, mfa_account), WRONG_CODE).status_code == 400
        assert events == []

    def test_a_store_outage_while_checking_the_lock_answers_503(self, state_outage, client, mfa_account):
        challenge = _start_mfa(client, mfa_account)
        state_outage()

        assert verify(client, challenge, mfa_account.backup_code).status_code == 503


class TestIdentityProviderMfaStep:
    def _challenge(self, client, committed_sessions, account) -> str:
        session_id = make_sso_session(committed_sessions, account.user)
        return exchange(client, session_id, headers=WEB).json()["mfa_challenge"]

    def test_an_unknown_device_is_refused_by_the_account_lock(self, client, committed_sessions, mfa_account):
        _lock_mfa(mfa_account)
        challenge = self._challenge(client, committed_sessions, mfa_account)

        response = verify(client, challenge, mfa_account.backup_code)

        assert response.status_code == 429
        row = audit_rows(committed_sessions, _LOGINS)[-1]
        assert (row.outcome, row.details["method"], row.details["reason"]) == (
            "denied",
            "identity_provider",
            "locked_out",
        )

    def test_a_known_device_completes_the_sign_in_and_lifts_the_lock(self, client, committed_sessions, mfa_account):
        _lock_mfa(mfa_account)
        device = _known_device(committed_sessions, mfa_account)
        challenge = self._challenge(client, committed_sessions, mfa_account)

        response = verify(client, challenge, mfa_account.backup_code, {**WEB, **device})

        assert response.status_code == 200
        assert not pending_mfa_store().is_locked_out(mfa_account.username, _IP, user_id=mfa_account.user.id)

    def test_the_hundredth_wrong_code_locks_and_tells_the_owner_once(
        self, client, committed_sessions, mfa_account, published
    ):
        events = published(authentication_events.MFA_LOCKED)
        _fail_codes(mfa_account, 99)
        challenge = self._challenge(client, committed_sessions, mfa_account)

        response = verify(client, challenge, WRONG_CODE)

        assert response.status_code == 400
        assert len(events) == 1
        assert [r.details for r in _locks(committed_sessions, "mfa_account")] == [
            {"counter": "mfa_account", "failed_attempts": 100}
        ]


class TestLiftingTheMfaLock:
    def test_an_administrator_resetting_mfa_lifts_the_lock_and_the_count(self, committed_sessions, mfa_account):
        _fail_codes(mfa_account, 99)
        _lock_mfa(mfa_account)

        with committed_sessions() as db:
            account_security_service.reset_managed_user_mfa(mfa_account.user.id, db)
            db.commit()

        store = pending_mfa_store()
        assert not store.is_locked_out(mfa_account.username, _IP, user_id=mfa_account.user.id)
        assert (
            store.record_failed_attempt(mfa_account.username, _IP, user_id=mfa_account.user.id).account_locked_now
            is False
        )

    def test_the_username_is_matched_regardless_of_case(self, mfa_account):
        store = pending_mfa_store()
        for i in range(100):
            store.record_failed_attempt("Alice", f"198.51.100.{i}", user_id=mfa_account.user.id)

        mfa_integration.clear_mfa_account_lockout(mfa_account.user.id)

        assert store.is_locked_out("Alice", _IP, user_id=mfa_account.user.id) is False

    def test_a_state_outage_does_not_fail_the_clear(self, state_outage, mfa_account):
        state_outage()

        mfa_integration.clear_mfa_account_lockout(mfa_account.user.id)

    def test_a_state_outage_does_not_fail_an_administrator_reset(self, state_outage, committed_sessions, mfa_account):
        state_outage()

        with committed_sessions() as db:
            account_security_service.reset_managed_user_mfa(mfa_account.user.id, db)
            db.commit()

        with committed_sessions() as db:
            assert mfa_integration.is_mfa_enabled_for_user(mfa_account.user.id, db) is False
