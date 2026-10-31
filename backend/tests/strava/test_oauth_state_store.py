"""The OAuth state is per user, expires, is single-use and fails loudly when storage is down."""

from unittest.mock import MagicMock

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
import pytest

import core.attempt_state as core_attempt_state
import modules.strava.oauth_state_store as strava_oauth_state_store


@pytest.fixture
def store():
    return strava_oauth_state_store.StravaOAuthStateStore(platform_runtime.get_state())


def test_the_stored_state_matches_once(store):
    store.begin(11, "abc")

    assert store.consume(11, "abc") is True
    assert store.consume(11, "abc") is False


def test_a_state_is_lost_to_another_user(store):
    store.begin(11, "abc")

    assert store.consume(12, "abc") is False
    assert store.consume(11, "abc") is True


def test_nothing_stored_never_matches(store):
    assert store.consume(13, "") is False


def test_the_state_expires_with_its_ttl():
    state = MagicMock()
    store = strava_oauth_state_store.StravaOAuthStateStore(state, ttl_seconds=600)

    store.begin(1, "abc")

    assert state.set.call_args.kwargs["ttl_seconds"] == 600


@pytest.mark.parametrize("call", [lambda s: s.begin(1, "a"), lambda s: s.consume(1, "a"), lambda s: s.clear(1)])
def test_an_unreachable_state_store_is_reported_not_swallowed(call):
    state = MagicMock()
    for method in ("set", "get_and_delete", "delete"):
        getattr(state, method).side_effect = platform_providers.StateBackendUnavailableError("down")

    with pytest.raises(core_attempt_state.StateUnavailableError):
        call(strava_oauth_state_store.StravaOAuthStateStore(state))
