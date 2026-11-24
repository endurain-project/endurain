"""The state-backed setup-token store, over the platform's own state provider."""

import jasil.runtime as platform_runtime
import pytest
from jasil.providers import StateBackendUnavailableError

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import modules.auth.onboarding.token_store as onboarding_token_store


@pytest.fixture
def store() -> onboarding_token_store.OnboardingTokenStore:
    return onboarding_token_store.OnboardingTokenStore(platform_runtime.get_state())


def test_an_issued_token_exists_until_it_is_claimed_once(store):
    token = store.issue()

    assert store.exists(token)
    assert store.exists(token), "checking a token must not consume it"
    assert store.claim(token) is True
    assert store.claim(token) is False
    assert not store.exists(token)


def test_an_unknown_token_does_not_exist_and_cannot_be_claimed(store):
    assert not store.exists("guess")
    assert store.claim("guess") is False


def test_each_token_is_unguessable_and_independent(store):
    first, second = store.issue(), store.issue()

    assert first != second
    assert len(first) >= 43
    assert store.claim(first) is True
    assert store.exists(second)


def test_only_a_digest_of_the_token_is_kept(store):
    token = store.issue()

    keys = list(platform_runtime.get_state().iter_keys("endurain:auth:onboarding:"))

    assert keys == [f"endurain:auth:onboarding:token:{core_hashing.sha256_hex(token)}"]
    assert token not in keys[0]


@pytest.mark.parametrize(("method", "operation"), [("set", "issue"), ("get", "exists"), ("get_and_delete", "claim")])
def test_a_state_outage_answers_service_unavailable(store, monkeypatch, method, operation):
    def down(*_args, **_kwargs):
        raise StateBackendUnavailableError("down")

    monkeypatch.setattr(platform_runtime.get_state(), method, down)

    with pytest.raises(core_exceptions.ServiceUnavailableError):
        getattr(store, operation)(*([] if operation == "issue" else ["token"]))
