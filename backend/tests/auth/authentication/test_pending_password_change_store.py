"""The shared-state store of pending password changes."""

import json
import uuid
from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import modules.auth.authentication.pending_password_change_store as pending_store
import modules.auth.constants as auth_constants

_USER_ID_12 = uuid.UUID(int=12)


def _record(**overrides) -> pending_store.PendingPasswordChange:
    fields = {
        "user_id": _USER_ID_12,
        "client_type": auth_constants.ClientType.MOBILE,
        "code_challenge": "c" * 43,
        "code_challenge_method": "S256",
        "mfa": True,
        "security_generation": 3,
    }
    return pending_store.PendingPasswordChange(**(fields | overrides))


def test_a_record_is_read_back_whole_and_claimed_once():
    store = pending_store.PendingPasswordChanges(MemoryState())
    challenge = store.add(_record())

    assert store.get(challenge) == _record()
    assert store.claim(challenge) == _record()
    assert store.claim(challenge) is None
    assert store.get(challenge) is None


def test_a_record_may_carry_no_pkce_values():
    store = pending_store.PendingPasswordChanges(MemoryState())
    record = _record(client_type=auth_constants.ClientType.WEB, code_challenge=None, code_challenge_method=None)

    assert store.get(store.add(record)) == record


def test_the_generation_is_stored_and_an_entry_written_without_one_reads_back_unstamped():
    state = MemoryState()
    store = pending_store.PendingPasswordChanges(state)
    challenge = store.add(_record())
    assert store.get(challenge).security_generation == 3

    (key,) = list(state.iter_keys(""))
    legacy = _record().model_dump(mode="json", exclude={"security_generation"})
    state.set(key, json.dumps(legacy).encode(), ttl_seconds=60)

    assert store.get(challenge).security_generation is None


def test_each_change_gets_its_own_256_bit_challenge():
    store = pending_store.PendingPasswordChanges(MemoryState())

    first, second = store.add(_record()), store.add(_record())

    assert first != second
    assert len(first) >= 43
    assert store.get("u" * 43) is None


def test_only_a_digest_of_the_challenge_is_kept_and_it_lives_ten_minutes():
    state = MagicMock()
    store = pending_store.PendingPasswordChanges(state)

    challenge = store.add(_record())

    key = state.set.call_args.args[0]
    assert challenge not in key
    assert state.set.call_args.kwargs == {"ttl_seconds": 600}


def test_a_corrupt_entry_is_removed_and_reads_as_unknown():
    state = MemoryState()
    store = pending_store.PendingPasswordChanges(state)
    challenge = store.add(_record())
    (key,) = list(state.iter_keys(""))
    state.set(key, b"not json", ttl_seconds=60)

    assert store.get(challenge) is None
    assert state.get(key) is None


@pytest.mark.parametrize("method", ["set", "get", "get_and_delete"])
def test_provider_failures_become_auth_store_errors(method):
    state = MagicMock()
    getattr(state, method).side_effect = StateBackendUnavailableError("down")
    store = pending_store.PendingPasswordChanges(state)

    with pytest.raises(pending_store.AuthSecurityStoreUnavailableError):
        {
            "set": lambda: store.add(_record()),
            "get": lambda: store.get("x"),
            "get_and_delete": lambda: store.claim("x"),
        }[method]()
