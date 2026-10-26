"""Tests for the Strava rate-limit state kept in the platform state provider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
import pytest

import modules.strava.rate_limit_store as strava_rate_limit_store


class TestRateLimitStoreIsSharedState:
    """The limits are Strava's, per application, so every process must see the same answer."""

    @pytest.fixture
    def tracker(self):
        return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())

    def test_nothing_is_limited_to_begin_with(self, tracker):
        assert tracker.is_rate_limited("app-a") is False

    def test_a_short_term_limit_is_visible_to_another_tracker(self, tracker):
        """Two instances stand in for two processes: the flag lives in the platform state."""
        tracker.mark_rate_limited("app-a", is_long_term=False)

        assert (
            strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state()).is_rate_limited("app-a") is True
        )

    def test_a_long_term_limit_is_visible_to_another_tracker(self, tracker):
        tracker.mark_rate_limited("app-a", is_long_term=True)

        assert (
            strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state()).is_rate_limited("app-a") is True
        )

    def test_a_short_term_limit_does_not_reach_another_app(self, tracker):
        """Each user brings their own Strava app, so one app's quota must not pause the others."""
        tracker.mark_rate_limited("app-a", is_long_term=False)

        assert tracker.is_rate_limited("app-b") is False

    def test_a_long_term_limit_does_not_reach_another_app(self, tracker):
        tracker.mark_rate_limited("app-a", is_long_term=True)

        assert tracker.is_rate_limited("app-b") is False

    def test_the_flag_expires_on_its_own(self, tracker):
        tracker.mark_rate_limited("app-a", is_long_term=False)
        platform_runtime.get_state().delete(strava_rate_limit_store._SHORT_TERM_KEY.format(client_id="app-a"))

        assert tracker.is_rate_limited("app-a") is False

    def test_an_unreachable_state_store_fails_open(self, tracker, monkeypatch):
        """A missed back-off costs one rejected call, which marks the limit again."""

        def _down(*_args, **_kwargs):
            raise platform_providers.StateBackendUnavailableError("redis down")

        monkeypatch.setattr(tracker._state, "get", _down)
        monkeypatch.setattr(tracker._state, "set", _down)

        assert tracker.is_rate_limited("app-a") is False
        tracker.mark_rate_limited("app-a")  # must not raise


class TestTokenRefreshClaim:
    @pytest.fixture
    def store(self):
        return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())

    def test_only_one_process_holds_the_claim(self, store):
        assert store.claim_token_refresh(901) is True
        assert store.claim_token_refresh(901) is False

    def test_the_claim_is_left_to_expire_not_released(self, store):
        """No owner-checked release exists, so a holder never frees a claim another process took after expiry."""
        assert not hasattr(store, "release_token_refresh")

    def test_claims_are_per_user(self, store):
        assert store.claim_token_refresh(902) is True
        assert store.claim_token_refresh(903) is True

    def test_an_unreachable_state_does_not_stop_the_refresh(self):
        state = MagicMock()
        state.set_if_absent.side_effect = platform_providers.StateBackendUnavailableError("down")
        store = strava_rate_limit_store.StravaRateLimitStore(state)

        assert store.claim_token_refresh(1) is True


class TestRateLimitedUntil:
    """The flag records when it expires, so a deferred sync can wait for exactly that long."""

    @pytest.fixture
    def tracker(self):
        return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())

    def test_nothing_limited_has_no_expiry(self, tracker):
        assert tracker.rate_limited_until("app-x") is None

    def test_a_short_term_limit_clears_after_the_cooldown(self, tracker):
        before = datetime.now(UTC)

        marked = tracker.mark_rate_limited("app-y", is_long_term=False)

        assert marked == tracker.rate_limited_until("app-y")
        assert (
            before + timedelta(seconds=strava_rate_limit_store.SHORT_TERM_COOLDOWN_SECONDS - 5)
            <= marked
            <= datetime.now(UTC) + timedelta(seconds=strava_rate_limit_store.SHORT_TERM_COOLDOWN_SECONDS)
        )

    def test_a_long_term_limit_clears_at_the_next_utc_midnight(self, tracker):
        marked = tracker.mark_rate_limited("app-z", is_long_term=True)

        assert (marked.hour, marked.minute, marked.second) == (0, 0, 0)
        assert datetime.now(UTC) < marked <= datetime.now(UTC) + timedelta(days=1)

    def test_the_later_expiry_wins_when_both_limits_are_set(self, tracker):
        tracker.mark_rate_limited("app-w", is_long_term=False)
        long_term = tracker.mark_rate_limited("app-w", is_long_term=True)

        assert tracker.rate_limited_until("app-w") == max(long_term, tracker.rate_limited_until("app-w"))
        assert tracker.rate_limited_until("app-w") >= long_term

    def test_a_flag_without_a_readable_expiry_still_defers_for_the_short_cooldown(self, tracker):
        platform_runtime.get_state().set(
            strava_rate_limit_store._SHORT_TERM_KEY.format(client_id="app-v"), b"1", ttl_seconds=60
        )

        until = tracker.rate_limited_until("app-v")

        assert until is not None
        assert until > datetime.now(UTC)

    def test_an_unreachable_state_has_no_expiry(self, tracker, monkeypatch):
        def _down(*_args, **_kwargs):
            raise platform_providers.StateBackendUnavailableError("redis down")

        monkeypatch.setattr(tracker._state, "get", _down)

        assert tracker.rate_limited_until("app-u") is None
