"""Tests for the state-backed setup-token store."""

from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import modules.auth.onboarding.token_store as onboarding_token_store


def test_an_issued_token_exists_until_it_is_claimed_once():
    store = onboarding_token_store.OnboardingTokenStore(MemoryState())
    token = store.issue()

    assert store.exists(token)
    assert store.exists(token), "checking a token must not consume it"
    assert store.claim(token) is True
    assert store.claim(token) is False
    assert not store.exists(token)


def test_an_unknown_token_does_not_exist_and_cannot_be_claimed():
    store = onboarding_token_store.OnboardingTokenStore(MemoryState())

    assert not store.exists("guess")
    assert store.claim("guess") is False


def test_each_token_is_unguessable_and_independent():
    store = onboarding_token_store.OnboardingTokenStore(MemoryState())

    first, second = store.issue(), store.issue()

    assert first != second
    assert len(first) >= 43
    assert store.claim(first) is True
    assert store.exists(second)


def test_only_a_digest_of_the_token_is_kept_and_it_expires_in_a_day():
    state = MagicMock()
    store = onboarding_token_store.OnboardingTokenStore(state)

    token = store.issue()

    key = state.set.call_args.args[0]
    assert token not in key
    assert key == f"endurain:auth:onboarding:token:{core_hashing.sha256_hex(token)}"
    assert state.set.call_args.kwargs == {"ttl_seconds": 24 * 60 * 60}
    assert onboarding_token_store.TOKEN_TTL_SECONDS == 24 * 60 * 60


@pytest.mark.parametrize(
    ("method", "operation"),
    [("set", "issue"), ("get", "exists"), ("get_and_delete", "claim")],
)
def test_a_state_outage_answers_service_unavailable(method, operation):
    state = MagicMock()
    getattr(state, method).side_effect = StateBackendUnavailableError("down")
    store = onboarding_token_store.OnboardingTokenStore(state)

    with pytest.raises(core_exceptions.ServiceUnavailableError):
        getattr(store, operation)(*([] if operation == "issue" else ["token"]))
