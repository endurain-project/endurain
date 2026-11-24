"""The date arithmetic of a health window: measured from the athlete's own today, which the caller passes in."""

from datetime import date, timedelta

import pytest

import modules.health.computation as health_computation
import modules.health.constants as health_constants

_ANCHOR = date(2026, 3, 15)


class TestGetStartDateForInterval:
    @pytest.mark.parametrize(
        ("interval", "days"),
        [("last_30_days", 30), ("last_90_days", 90), ("last_year", 365), ("last_7_days", 7), ("unknown", 7)],
    )
    def test_the_window_looks_back_from_the_anchor(self, interval, days):
        assert health_computation.get_start_date_for_interval(interval, _ANCHOR) == _ANCHOR - timedelta(days=days)

    def test_all_time_starts_at_the_earliest_date(self):
        assert health_computation.get_start_date_for_interval("all_time", _ANCHOR) == date.min

    def test_the_anchor_drives_the_window_not_the_server_clock(self):
        east = health_computation.get_start_date_for_interval("last_7_days", date(2026, 3, 16))
        west = health_computation.get_start_date_for_interval("last_7_days", date(2026, 3, 15))

        assert east - west == timedelta(days=1)


class TestIntervalStart:
    def test_no_interval_means_no_lower_bound_and_no_calendar_lookup(self):
        def fail() -> date:
            raise AssertionError("today must not be read without an interval")

        assert health_computation.interval_start(None, fail) is None

    def test_an_interval_starts_before_the_users_own_today(self):
        start = health_computation.interval_start(health_constants.Interval.LAST_30_DAYS, lambda: _ANCHOR)

        assert start == _ANCHOR - timedelta(days=30)
