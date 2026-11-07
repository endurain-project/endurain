"""Tests for the Garmin Connect rate-limit state kept in the platform state provider."""

from datetime import UTC, datetime, timedelta

from jasil.backends.state_memory import MemoryState

import modules.garmin.constants as garmin_constants
import modules.garmin.rate_limit_store as garmin_rate_limit_store


def test_nothing_is_limited_to_begin_with():
    store = garmin_rate_limit_store.GarminRateLimitStore(MemoryState())

    assert store.rate_limited_until(1) is None


def test_a_limit_lasts_one_cooldown_and_is_visible_to_another_replica():
    state = MemoryState()
    before = datetime.now(UTC)

    until = garmin_rate_limit_store.GarminRateLimitStore(state).mark_rate_limited(1)

    assert before + timedelta(seconds=garmin_constants.RATE_LIMIT_COOLDOWN_SECONDS) <= until
    assert garmin_rate_limit_store.GarminRateLimitStore(state).rate_limited_until(1) == until


def test_the_limit_is_per_user():
    store = garmin_rate_limit_store.GarminRateLimitStore(MemoryState())
    store.mark_rate_limited(1)

    assert store.rate_limited_until(2) is None
