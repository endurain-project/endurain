"""Tests for the provider-backed pending-MFA login store."""

import json
from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import modules.auth.constants as auth_constants
import modules.auth.mfa.pending_login_store as pending_mfa
from tests._helpers.auth import pending_login


def test_pending_login_lifecycle_and_atomic_claim():
    store = pending_mfa.PendingMFALogin(MemoryState())
    pending = pending_login(12, auth_constants.ClientType.MOBILE, "c" * 43, "S256")
    challenge = store.add_pending_login(pending)

    assert store.get_pending_login(challenge) == pending
    assert store.claim_pending_login(challenge) == pending
    assert store.get_pending_login(challenge) is None


def test_the_record_keeps_the_client_network_of_the_password_step():
    store = pending_mfa.PendingMFALogin(MemoryState())
    challenge = store.add_pending_login(pending_login(12, client_network="2001:db8:1:2::/64"))

    record = store.get_pending_login(challenge)

    assert record is not None
    assert record.client_network == "2001:db8:1:2::/64"


def test_the_record_keeps_the_client_type_and_the_pkce_values_of_the_password_step():
    store = pending_mfa.PendingMFALogin(MemoryState())
    challenge = store.add_pending_login(pending_login(12, auth_constants.ClientType.MOBILE, "c" * 43, "S256"))

    record = store.get_pending_login(challenge)

    assert record is not None
    assert record.client_type == auth_constants.ClientType.MOBILE
    assert (record.code_challenge, record.code_challenge_method) == ("c" * 43, "S256")


@pytest.mark.parametrize("stored", [b"12", b"not json", b'{"user_id": 12}'])
def test_a_corrupt_entry_is_refused_and_removed(stored):
    state = MemoryState()
    store = pending_mfa.PendingMFALogin(state)
    challenge = "corrupt"
    state.set(store._pending_key(challenge), stored, ttl_seconds=60)

    assert store.get_pending_login(challenge) is None
    assert state.get(store._pending_key(challenge)) is None


def test_each_login_gets_its_own_unguessable_challenge():
    """The challenge, not the username, names the login, so knowing a username grants nothing."""
    store = pending_mfa.PendingMFALogin(MemoryState())

    first, second = store.add_pending_login(pending_login(12)), store.add_pending_login(pending_login(12))

    assert first != second
    assert len(first) >= 43
    assert store.get_pending_login("alice") is None


def test_only_a_digest_of_the_challenge_is_kept():
    state = MagicMock()
    store = pending_mfa.PendingMFALogin(state)

    pending = pending_login(12)
    challenge = store.add_pending_login(pending)

    key = state.set.call_args.args[0]
    assert challenge not in key
    state.set.assert_called_once_with(
        store._pending_key(challenge), pending.model_dump_json().encode(), ttl_seconds=300
    )


def test_the_record_keeps_the_security_generation_and_an_entry_without_one_reads_back_unstamped():
    state = MemoryState()
    store = pending_mfa.PendingMFALogin(state)
    challenge = store.add_pending_login(pending_login(12, security_generation=5))
    assert store.get_pending_login(challenge).security_generation == 5

    legacy = pending_login(12).model_dump(exclude={"security_generation"})
    state.set(store._pending_key(challenge), json.dumps(legacy).encode(), ttl_seconds=60)

    assert store.get_pending_login(challenge).security_generation is None


class TestWrongCodes:
    def test_the_challenge_ends_on_the_last_allowed_wrong_code(self):
        state = MemoryState()
        store = pending_mfa.PendingMFALogin(state)
        challenge = store.add_pending_login(pending_login(12))

        ended = [store.record_wrong_code(challenge) for _ in range(pending_mfa.MFA_CHALLENGE_MAX_ATTEMPTS)]

        assert ended == [False] * (pending_mfa.MFA_CHALLENGE_MAX_ATTEMPTS - 1) + [True]
        assert pending_mfa.MFA_CHALLENGE_MAX_ATTEMPTS == 3
        assert store.get_pending_login(challenge) is None
        assert state.get(store._attempts_key(challenge)) is None

    def test_a_challenge_below_the_cap_stays_pending(self):
        store = pending_mfa.PendingMFALogin(MemoryState())
        challenge = store.add_pending_login(pending_login(12))

        store.record_wrong_code(challenge)

        assert store.get_pending_login(challenge) == pending_login(12)

    def test_the_count_is_kept_under_its_own_prefix_with_the_pending_ttl(self):
        state = MagicMock()
        state.incr.return_value = 1
        store = pending_mfa.PendingMFALogin(state)

        store.record_wrong_code("challenge")

        key = state.incr.call_args.args[0]
        assert key.startswith("endurain:auth:mfa:challenge-attempts:")
        assert not key.startswith("endurain:auth:mfa:pending")
        assert "challenge" not in key.removeprefix("endurain:auth:mfa:challenge-attempts:")
        assert state.incr.call_args.kwargs == {"ttl_seconds": 300}

    def test_a_claim_removes_the_count(self):
        state = MemoryState()
        store = pending_mfa.PendingMFALogin(state)
        challenge = store.add_pending_login(pending_login(12))
        store.record_wrong_code(challenge)

        assert store.claim_pending_login(challenge) == pending_login(12)

        assert state.get(store._attempts_key(challenge)) is None

    def test_clear_all_removes_the_pending_logins_and_their_counts(self):
        state = MemoryState()
        store = pending_mfa.PendingMFALogin(state)
        challenge = store.add_pending_login(pending_login(12))
        store.record_wrong_code(challenge)

        store.clear_all()

        assert state.get(store._attempts_key(challenge)) is None
        assert store.get_pending_login(challenge) is None


@pytest.mark.parametrize(
    ("method", "operation"),
    [
        ("set", "add"),
        ("get", "get"),
        ("get_and_delete", "claim"),
        ("delete", "delete_corrupt"),
        ("delete_prefix", "clear_all"),
        ("incr", "wrong_code"),
    ],
)
def test_provider_failures_become_auth_store_errors(method, operation):
    state = MagicMock()
    getattr(state, method).side_effect = StateBackendUnavailableError("down")
    store = pending_mfa.PendingMFALogin(state)

    with pytest.raises(pending_mfa.AuthSecurityStoreUnavailableError):
        if operation == "add":
            store.add_pending_login(pending_login(12))
        elif operation == "get":
            store.get_pending_login("challenge")
        elif operation == "claim":
            store.claim_pending_login("challenge")
        elif operation == "delete_corrupt":
            state.get.return_value = b"invalid-record"
            store.get_pending_login("challenge")
        elif operation == "wrong_code":
            store.record_wrong_code("challenge")
        else:
            store.clear_all()


def test_dependency_builds_store_from_provided_state():
    state = MemoryState()

    store = pending_mfa.get_pending_mfa_store(state)

    assert isinstance(store, pending_mfa.PendingMFALogin)
    assert store._state is state
