"""The Strava rate limits and token-refresh claims are shared state: every process must see the same answer."""

import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as platform_runtime
import pytest

import modules.strava.rate_limit_store as strava_rate_limit_store
from tests._factories.strava import UnavailableState


@pytest.fixture
def tracker():
    return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())


def _another_process():
    """A second store over the same platform state, as another worker or replica would hold."""
    return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())


class TestRateLimits:
    def test_nothing_is_limited_to_begin_with(self, tracker):
        assert tracker.is_rate_limited("app-a") is False
        assert tracker.rate_limited_until("app-a") is None

    @pytest.mark.parametrize("is_long_term", [False, True])
    def test_a_limit_is_visible_to_another_process(self, tracker, is_long_term):
        tracker.mark_rate_limited("app-a", is_long_term=is_long_term)

        assert _another_process().is_rate_limited("app-a") is True

    @pytest.mark.parametrize("is_long_term", [False, True])
    def test_one_application_hitting_its_limit_does_not_pause_another(self, tracker, is_long_term):
        tracker.mark_rate_limited("app-a", is_long_term=is_long_term)

        assert tracker.is_rate_limited("app-b") is False

    def test_the_limit_expires_on_its_own(self, tracker, advance_state_clock):
        tracker.mark_rate_limited("app-a", is_long_term=False)

        advance_state_clock(strava_rate_limit_store.SHORT_TERM_COOLDOWN_SECONDS + 1)

        assert tracker.is_rate_limited("app-a") is False

    def test_a_short_term_limit_clears_after_the_cooldown(self, tracker):
        before = datetime.now(UTC)

        marked = tracker.mark_rate_limited("app-y", is_long_term=False)

        assert marked == tracker.rate_limited_until("app-y")
        cooldown = timedelta(seconds=strava_rate_limit_store.SHORT_TERM_COOLDOWN_SECONDS)
        assert before + cooldown <= marked <= datetime.now(UTC) + cooldown

    def test_a_long_term_limit_clears_at_the_next_utc_midnight(self, tracker):
        marked = tracker.mark_rate_limited("app-z", is_long_term=True)

        assert (marked.hour, marked.minute, marked.second) == (0, 0, 0)
        assert datetime.now(UTC) < marked <= datetime.now(UTC) + timedelta(days=1)

    def test_the_later_expiry_wins_when_both_limits_are_set(self, tracker):
        short = tracker.mark_rate_limited("app-w", is_long_term=False)
        long_term = tracker.mark_rate_limited("app-w", is_long_term=True)

        assert tracker.rate_limited_until("app-w") == max(short, long_term)

    def test_a_flag_without_a_readable_expiry_still_defers_for_the_short_cooldown(self, tracker):
        platform_runtime.get_state().set("strava:rate_limited:short:app-v", b"not a date", ttl_seconds=60)

        until = tracker.rate_limited_until("app-v")

        assert until is not None
        assert until > datetime.now(UTC)

    def test_an_unreachable_state_store_fails_open(self):
        down = strava_rate_limit_store.StravaRateLimitStore(UnavailableState())

        assert down.is_rate_limited("app-a") is False
        assert down.rate_limited_until("app-a") is None
        down.mark_rate_limited("app-a")  # a missed back-off costs one rejected call, which marks it again


class TestTokenRefreshClaim:
    def test_only_one_process_holds_the_claim(self, tracker):
        user_id = uuid.uuid4()

        assert tracker.claim_token_refresh(user_id) is True
        assert _another_process().claim_token_refresh(user_id) is False

    def test_claims_are_per_user(self, tracker):
        assert tracker.claim_token_refresh(uuid.uuid4()) is True
        assert tracker.claim_token_refresh(uuid.uuid4()) is True

    def test_a_released_claim_can_be_taken_again(self, tracker):
        user_id = uuid.uuid4()
        tracker.claim_token_refresh(user_id)

        tracker.release_token_refresh(user_id)

        assert tracker.claim_token_refresh(user_id) is True

    def test_a_claim_expires_on_its_own(self, tracker, advance_state_clock):
        user_id = uuid.uuid4()
        tracker.claim_token_refresh(user_id)

        advance_state_clock(3600)

        assert tracker.claim_token_refresh(user_id) is True

    def test_an_unreachable_state_does_not_stop_the_refresh_or_fail_the_release(self):
        down = strava_rate_limit_store.StravaRateLimitStore(UnavailableState())
        user_id = uuid.uuid4()

        assert down.claim_token_refresh(user_id) is True
        down.release_token_refresh(user_id)
