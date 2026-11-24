"""The OAuth state is per user, expires, is single-use and fails loudly when storage is down."""

import uuid

import jasil.runtime as platform_runtime
import pytest

import core.attempt_state as core_attempt_state
import modules.strava.constants as strava_constants
import modules.strava.oauth_state_store as strava_oauth_state_store
from tests._factories.strava import UnavailableState


@pytest.fixture
def store():
    return strava_oauth_state_store.StravaOAuthStateStore(platform_runtime.get_state())


def test_the_stored_state_matches_once(store):
    user_id = uuid.uuid4()
    store.begin(user_id, "abc")

    assert store.consume(user_id, "abc") is True
    assert store.consume(user_id, "abc") is False


def test_a_state_stored_for_one_user_is_useless_to_another(store):
    owner, other = uuid.uuid4(), uuid.uuid4()
    store.begin(owner, "abc")

    assert store.consume(other, "abc") is False
    assert store.consume(owner, "abc") is True


def test_a_wrong_guess_uses_the_state_up(store):
    user_id = uuid.uuid4()
    store.begin(user_id, "abc")

    assert store.consume(user_id, "abd") is False
    assert store.consume(user_id, "abc") is False


def test_a_new_state_replaces_the_old_one(store):
    user_id = uuid.uuid4()
    store.begin(user_id, "first")
    store.begin(user_id, "second")

    assert store.consume(user_id, "first") is False


def test_nothing_stored_never_matches(store):
    assert store.consume(uuid.uuid4(), "") is False


def test_the_state_expires_after_its_lifetime(store, advance_state_clock):
    user_id = uuid.uuid4()
    store.begin(user_id, "abc")

    advance_state_clock(strava_constants.OAUTH_STATE_TTL_SECONDS + 1)

    assert store.consume(user_id, "abc") is False


@pytest.mark.parametrize("call", [lambda s, user: s.begin(user, "a"), lambda s, user: s.consume(user, "a")])
def test_an_unreachable_state_store_is_reported_not_swallowed(call):
    store = strava_oauth_state_store.StravaOAuthStateStore(UnavailableState())

    with pytest.raises(core_attempt_state.StateUnavailableError):
        call(store, uuid.uuid4())
