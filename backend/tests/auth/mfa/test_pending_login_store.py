"""Tests for the provider-backed pending-MFA login store."""

from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import modules.auth.mfa.pending_login_store as pending_mfa


def test_pending_login_lifecycle_and_atomic_claim():
    store = pending_mfa.PendingMFALogin(MemoryState())
    store.add_pending_login(" Alice ", 12)

    assert store.get_pending_login("alice") == 12
    assert store.has_pending_login("ALICE")
    assert store.claim_pending_login("alice") == 12
    assert store.get_pending_login("alice") is None


def test_pending_login_uses_five_minute_ttl():
    state = MagicMock()
    store = pending_mfa.PendingMFALogin(state)

    store.add_pending_login("alice", 12)

    state.set.assert_called_once_with(store._pending_key("alice"), b"12", ttl_seconds=300)


def test_clear_for_user_removes_only_matching_user_entries():
    state = MemoryState()
    store = pending_mfa.PendingMFALogin(state)
    store.add_pending_login("alice", 12)
    store.add_pending_login("bob", 34)

    assert store.clear_for_user(12) == 1
    assert store.get_pending_login("alice") is None
    assert store.get_pending_login("bob") == 34


@pytest.mark.parametrize(
    ("method", "operation"),
    [
        ("set", "add"),
        ("get", "get"),
        ("get_and_delete", "claim"),
        ("delete", "delete_corrupt"),
        ("iter_keys", "clear_for_user"),
        ("delete_prefix", "clear_all"),
    ],
)
def test_provider_failures_become_auth_store_errors(method, operation):
    state = MagicMock()
    getattr(state, method).side_effect = StateBackendUnavailableError("down")
    store = pending_mfa.PendingMFALogin(state)

    with pytest.raises(pending_mfa.AuthSecurityStoreUnavailableError):
        if operation == "add":
            store.add_pending_login("alice", 12)
        elif operation == "get":
            store.get_pending_login("alice")
        elif operation == "claim":
            store.claim_pending_login("alice")
        elif operation == "delete_corrupt":
            state.get.return_value = b"invalid-user-id"
            store.get_pending_login("alice")
        elif operation == "clear_for_user":
            store.clear_for_user(12)
        else:
            store.clear_all()


def test_clear_pending_mfa_for_user_tolerates_state_outage():
    state = MagicMock()
    state.iter_keys.side_effect = StateBackendUnavailableError("down")

    assert pending_mfa.clear_pending_mfa_for_user(state, 12) == 0


def test_dependency_builds_store_from_provided_state():
    state = MemoryState()

    store = pending_mfa.get_pending_mfa_store(state)

    assert isinstance(store, pending_mfa.PendingMFALogin)
    assert store._state is state
