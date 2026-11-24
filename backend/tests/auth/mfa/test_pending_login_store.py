"""Tests for the provider-backed pending-MFA login store."""

import json
import uuid

import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState

import core.network as core_network
import modules.auth.constants as auth_constants
import modules.auth.mfa.pending_login_store as pending_mfa
from tests._factories.state import DownState
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID, pending_login


def test_pending_login_lifecycle_and_atomic_claim():
    store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
    pending = pending_login(MOCK_USER_ID, auth_constants.ClientType.MOBILE, "c" * 43, "S256")
    challenge = store.add_pending_login(pending)

    assert store.get_pending_login(challenge) == pending
    assert store.claim_pending_login(challenge) == pending
    assert store.get_pending_login(challenge) is None


def test_the_record_keeps_the_client_network_of_the_password_step():
    store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
    challenge = store.add_pending_login(pending_login(MOCK_USER_ID, client_network="2001:db8:1:2::/64"))

    record = store.get_pending_login(challenge)

    assert record is not None
    assert record.client_network == "2001:db8:1:2::/64"


def test_the_record_keeps_the_client_type_and_the_pkce_values_of_the_password_step():
    store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
    challenge = store.add_pending_login(pending_login(MOCK_USER_ID, auth_constants.ClientType.MOBILE, "c" * 43, "S256"))

    record = store.get_pending_login(challenge)

    assert record is not None
    assert record.client_type == auth_constants.ClientType.MOBILE
    assert (record.code_challenge, record.code_challenge_method) == ("c" * 43, "S256")


def test_a_password_sign_in_names_no_sso_session():
    store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
    challenge = store.add_pending_login(pending_login(MOCK_USER_ID))

    record = store.get_pending_login(challenge)

    assert record is not None
    assert record.sso_session_id is None


def test_the_record_keeps_the_sso_session_it_finishes():
    store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
    session_id = uuid.uuid4()
    challenge = store.add_pending_login(pending_login(MOCK_USER_ID).model_copy(update={"sso_session_id": session_id}))

    record = store.claim_pending_login(challenge)

    assert record is not None
    assert record.sso_session_id == session_id


@pytest.mark.parametrize("stored", [b"12", b"not json", b'{"user_id": 12}'])
def test_a_corrupt_entry_is_refused_and_removed(stored):
    state = MemoryState(jasil_testing.FixedClock())
    store = pending_mfa.PendingMFALogin(state)
    challenge = "corrupt"
    state.set(store._pending_key(challenge), stored, ttl_seconds=60)

    assert store.get_pending_login(challenge) is None
    assert state.get(store._pending_key(challenge)) is None


def test_each_login_gets_its_own_unguessable_challenge():
    """The challenge, not the username, names the login, so knowing a username grants nothing."""
    store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))

    first, second = (
        store.add_pending_login(pending_login(MOCK_USER_ID)),
        store.add_pending_login(pending_login(MOCK_USER_ID)),
    )

    assert first != second
    assert len(first) >= 43
    assert store.get_pending_login("alice") is None


def test_only_a_digest_of_the_challenge_is_kept():
    state = MemoryState(jasil_testing.FixedClock())
    store = pending_mfa.PendingMFALogin(state)

    pending = pending_login(MOCK_USER_ID)
    challenge = store.add_pending_login(pending)

    key = store._pending_key(challenge)
    assert challenge not in key
    assert state.get(key) == pending.model_dump_json().encode()


def test_the_record_keeps_the_security_generation_and_an_entry_without_one_reads_back_unstamped():
    state = MemoryState(jasil_testing.FixedClock())
    store = pending_mfa.PendingMFALogin(state)
    challenge = store.add_pending_login(pending_login(MOCK_USER_ID, security_generation=5))
    assert store.get_pending_login(challenge).security_generation == 5

    legacy = pending_login(MOCK_USER_ID).model_dump(mode="json", exclude={"security_generation"})
    state.set(store._pending_key(challenge), json.dumps(legacy).encode(), ttl_seconds=60)

    assert store.get_pending_login(challenge).security_generation is None


class TestWrongCodes:
    def test_the_challenge_ends_on_the_last_allowed_wrong_code(self):
        state = MemoryState(jasil_testing.FixedClock())
        store = pending_mfa.PendingMFALogin(state)
        challenge = store.add_pending_login(pending_login(MOCK_USER_ID))

        ended = [store.record_wrong_code(challenge) for _ in range(pending_mfa.MFA_CHALLENGE_MAX_ATTEMPTS)]

        assert ended == [False] * (pending_mfa.MFA_CHALLENGE_MAX_ATTEMPTS - 1) + [True]
        assert pending_mfa.MFA_CHALLENGE_MAX_ATTEMPTS == 3
        assert store.get_pending_login(challenge) is None
        assert state.get(store._attempts_key(challenge)) is None

    def test_a_challenge_below_the_cap_stays_pending(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        challenge = store.add_pending_login(pending_login(MOCK_USER_ID))

        store.record_wrong_code(challenge)

        assert store.get_pending_login(challenge) == pending_login(MOCK_USER_ID)

    def test_the_count_is_kept_under_its_own_prefix_and_never_names_the_challenge(self):
        state = MemoryState(jasil_testing.FixedClock())
        store = pending_mfa.PendingMFALogin(state)
        challenge = store.add_pending_login(pending_login(MOCK_USER_ID))

        store.record_wrong_code(challenge)

        key = store._attempts_key(challenge)
        assert key.startswith("endurain:auth:mfa:challenge-attempts:")
        assert not key.startswith("endurain:auth:mfa:pending")
        assert challenge not in key
        assert state.get(key) is not None

    def test_a_claim_removes_the_count(self):
        state = MemoryState(jasil_testing.FixedClock())
        store = pending_mfa.PendingMFALogin(state)
        challenge = store.add_pending_login(pending_login(MOCK_USER_ID))
        store.record_wrong_code(challenge)

        assert store.claim_pending_login(challenge) == pending_login(MOCK_USER_ID)

        assert state.get(store._attempts_key(challenge)) is None

    def test_clear_all_removes_the_pending_logins_and_their_counts(self):
        state = MemoryState(jasil_testing.FixedClock())
        store = pending_mfa.PendingMFALogin(state)
        challenge = store.add_pending_login(pending_login(MOCK_USER_ID))
        store.record_wrong_code(challenge)

        store.clear_all()

        assert state.get(store._attempts_key(challenge)) is None
        assert store.get_pending_login(challenge) is None


@pytest.mark.parametrize("operation", ["add", "get", "claim", "wrong_code", "clear_all"])
def test_provider_failures_become_auth_store_errors(operation):
    store = pending_mfa.PendingMFALogin(DownState())

    with pytest.raises(pending_mfa.AuthSecurityStoreUnavailableError):
        if operation == "add":
            store.add_pending_login(pending_login(MOCK_USER_ID))
        elif operation == "get":
            store.get_pending_login("challenge")
        elif operation == "claim":
            store.claim_pending_login("challenge")
        elif operation == "wrong_code":
            store.record_wrong_code("challenge")
        else:
            store.clear_all()


_UID = MOCK_USER_ID
_IP = "203.0.113.5"
_OTHER_IP = "198.51.100.9"


def _client_key(username: str = "alice", ip_address: str = _IP) -> str:
    return f"{username}|{core_network.client_network(ip_address)}"


def _lock_account(store: pending_mfa.PendingMFALogin, username: str = "alice", *, keep_tiered: bool = False) -> None:
    """Record the wrong codes that reach the account-wide cap, leaving the tiered lock open unless asked to keep it."""
    for _ in range(100):
        store.record_failed_attempt(username, _IP, user_id=_UID)
    if not keep_tiered:
        store._lockout.reset_attempts(_client_key(username.casefold()))


class TestAccountWideLock:
    def test_the_hundredth_wrong_code_locks_the_account_and_no_earlier_one_does(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))

        records = [store.record_failed_attempt("alice", _IP, user_id=_UID) for _ in range(100)]

        assert [r.account_locked_now for r in records] == [False] * 99 + [True]

    def test_the_tiered_count_is_reported_not_the_account_count(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))

        store.record_failed_attempt("alice", _IP, user_id=_UID)
        store.reset_account(_UID)
        record = store.record_failed_attempt("alice", _IP, user_id=_UID)

        assert record == pending_mfa.FailedMfaRecord(count=2, account_locked_now=False)

    def test_the_lock_holds_an_unknown_device_for_thirty_days(self):
        clock = jasil_testing.FixedClock()
        store = pending_mfa.PendingMFALogin(MemoryState(clock))
        _lock_account(store)

        until = store.get_lockout_time("Alice", _IP, user_id=_UID)

        assert store.is_locked_out("alice", _IP, user_id=_UID) is True
        assert until is not None
        assert abs((until - clock.now()).total_seconds() - 30 * 24 * 60 * 60) < 60

    def test_a_known_device_ignores_the_account_lock(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        _lock_account(store)

        assert store.is_locked_out("alice", _IP, known_device=True, user_id=_UID) is False
        assert store.get_lockout_time("alice", _IP, known_device=True, user_id=_UID) is None

    def test_a_known_device_is_still_held_by_the_tiered_lock(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        for _ in range(5):
            store.record_failed_attempt("alice", _IP, user_id=_UID)

        assert store.is_locked_out("alice", _IP, known_device=True, user_id=_UID) is True
        assert store.get_lockout_time("alice", _IP, known_device=True, user_id=_UID) is not None

    def test_the_later_of_the_two_expiries_is_reported(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        _lock_account(store, keep_tiered=True)

        tiered = store._lockout.get_lockout_time(_client_key())
        account = store._by_account.get_lockout_time(str(_UID))

        assert tiered is not None
        assert account is not None
        assert tiered < account
        assert store.get_lockout_time("alice", _IP, user_id=_UID) == account
        assert store.get_lockout_time("alice", _IP, known_device=True, user_id=_UID) == tiered

    def test_the_account_lock_is_keyed_on_the_normalized_username(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        _lock_account(store, "Alice")

        assert store.is_locked_out("  alice ", _IP, user_id=_UID) is True

    def test_reset_account_clears_only_the_account_counter(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        _lock_account(store, keep_tiered=True)

        store.reset_account(_UID)

        assert store._by_account.get_lockout_time(str(_UID)) is None
        assert store._lockout.get_lockout_time(_client_key()) is not None
        assert store.record_failed_attempt("alice", _IP, user_id=_UID).account_locked_now is False

    def test_reset_attempts_clears_both_counters(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        _lock_account(store, keep_tiered=True)

        store.reset_attempts("alice", _IP, user_id=_UID)

        assert store.is_locked_out("alice", _IP, user_id=_UID) is False
        assert store.record_failed_attempt("alice", _IP, user_id=_UID) == pending_mfa.FailedMfaRecord(
            count=1, account_locked_now=False
        )

    def test_clear_all_clears_both_counters(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        _lock_account(store, keep_tiered=True)
        _lock_account(store, "bob", keep_tiered=True)

        store.clear_all()

        assert store.is_locked_out("alice", _IP, user_id=_UID) is False
        assert store.is_locked_out("bob", _IP, user_id=_UID) is False
        assert store.record_failed_attempt("alice", _IP, user_id=_UID).count == 1

    def test_a_provider_outage_becomes_an_auth_store_error(self):
        store = pending_mfa.PendingMFALogin(DownState())

        with pytest.raises(pending_mfa.AuthSecurityStoreUnavailableError):
            store.record_failed_attempt("alice", _IP, user_id=_UID)


class TestTieredLockPerNetwork:
    def test_wrong_codes_lock_only_their_own_network(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        for _ in range(5):
            store.record_failed_attempt("alice", _IP, user_id=_UID)

        assert store.is_locked_out("alice", _IP, user_id=_UID) is True
        assert store.is_locked_out("alice", _OTHER_IP, user_id=_UID) is False
        assert store.get_lockout_time("alice", _OTHER_IP, user_id=_UID) is None

    def test_every_address_of_an_ipv6_64_is_one_network(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        for _ in range(5):
            store.record_failed_attempt("alice", "2001:db8:1:2::1", user_id=_UID)

        assert store.is_locked_out("alice", "2001:db8:1:2:ffff::9", user_id=_UID) is True
        assert store.is_locked_out("alice", "2001:db8:1:3::1", user_id=_UID) is False

    def test_the_account_lock_holds_every_network(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        _lock_account(store)

        assert store.is_locked_out("alice", _OTHER_IP, user_id=_UID) is True
        assert store.is_locked_out("alice", _OTHER_IP, known_device=True, user_id=_UID) is False

    def test_a_wrong_code_counts_toward_the_account_from_every_network(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))

        records = [store.record_failed_attempt("alice", f"198.51.100.{i}", user_id=_UID) for i in range(100)]

        assert [r.count for r in records] == [1] * 100
        assert records[-1].account_locked_now is True

    def test_a_success_clears_its_own_network_and_the_account_only(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        for _ in range(5):
            store.record_failed_attempt("alice", _IP, user_id=_UID)
            store.record_failed_attempt("alice", _OTHER_IP, user_id=_UID)

        store.reset_attempts("alice", _IP, user_id=_UID)

        assert store.is_locked_out("alice", _IP, user_id=_UID) is False
        assert store.is_locked_out("alice", _OTHER_IP, user_id=_UID) is True


class TestRenamedAccount:
    def test_the_account_lock_follows_the_user_id_across_a_username_change(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        _lock_account(store)

        assert store.is_locked_out("alicia", _OTHER_IP, user_id=_UID) is True
        assert store.is_locked_out("alicia", _OTHER_IP, user_id=_UID, known_device=True) is False

    def test_the_account_lock_is_not_held_by_another_user_id(self):
        store = pending_mfa.PendingMFALogin(MemoryState(jasil_testing.FixedClock()))
        _lock_account(store)

        assert store.is_locked_out("alice", _OTHER_IP, user_id=OTHER_USER_ID) is False
