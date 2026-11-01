from datetime import date, timedelta
from types import SimpleNamespace

import modules.health.computation as health_computation
import modules.health.health_steps.schema as health_steps_schema


class TestGetStartDateForInterval:
    """Windows are measured from the athlete's own today, passed in by the caller.

    Reading the server clock here made every interval filter shift by a day for
    users east/west of the container's timezone.
    """

    ANCHOR = date(2026, 3, 15)

    def test_last_30_days(self):
        from modules.health.computation import get_start_date_for_interval

        assert get_start_date_for_interval("last_30_days", self.ANCHOR) == self.ANCHOR - timedelta(days=30)

    def test_last_90_days(self):
        from modules.health.computation import get_start_date_for_interval

        assert get_start_date_for_interval("last_90_days", self.ANCHOR) == self.ANCHOR - timedelta(days=90)

    def test_last_year(self):
        from modules.health.computation import get_start_date_for_interval

        assert get_start_date_for_interval("last_year", self.ANCHOR) == self.ANCHOR - timedelta(days=365)

    def test_all_time(self):
        from modules.health.computation import get_start_date_for_interval

        assert get_start_date_for_interval("all_time", self.ANCHOR) == date.min

    def test_default(self):
        from modules.health.computation import get_start_date_for_interval

        assert get_start_date_for_interval("unknown", self.ANCHOR) == self.ANCHOR - timedelta(days=7)

    def test_anchor_drives_the_window_not_the_server_clock(self):
        """Two callers on different calendar days get different windows."""
        from modules.health.computation import get_start_date_for_interval

        east = get_start_date_for_interval("last_7_days", date(2026, 3, 16))
        west = get_start_date_for_interval("last_7_days", date(2026, 3, 15))
        assert east - west == timedelta(days=1)


class TestIntervalEnum:
    def test_values(self):
        from modules.health.constants import Interval

        assert Interval.LAST_7_DAYS.value == "last_7_days"
        assert Interval.LAST_30_DAYS.value == "last_30_days"
        assert Interval.LAST_90_DAYS.value == "last_90_days"
        assert Interval.LAST_YEAR.value == "last_year"
        assert Interval.ALL_TIME.value == "all_time"


class TestIntervalStart:
    """A list request's interval is resolved against the user's own calendar."""

    def test_no_interval_means_no_lower_bound_and_no_calendar_lookup(self):
        from modules.health.computation import interval_start

        def fail() -> date:
            raise AssertionError("today must not be read without an interval")

        assert interval_start(None, fail) is None

    def test_an_interval_starts_before_the_users_own_today(self):
        from modules.health.computation import interval_start
        from modules.health.constants import Interval

        today = date(2026, 3, 15)

        assert interval_start(Interval.LAST_30_DAYS, lambda: today) == today - timedelta(days=30)


class TestToReadSchema:
    def test_validates_a_row_against_the_given_schema(self):
        row = SimpleNamespace(id=1, version=2, user_id=3, date=date(2024, 1, 15), steps=9000, source=None)

        result = health_computation.to_read_schema(health_steps_schema.HealthStepsRead, row)

        assert isinstance(result, health_steps_schema.HealthStepsRead)
        assert result.steps == 9000

    def test_converts_every_row_in_order(self):
        rows = [
            SimpleNamespace(id=i, version=1, user_id=3, date=date(2024, 1, i), steps=i, source=None) for i in (1, 2)
        ]

        assert [r.id for r in health_computation.to_read_schemas(health_steps_schema.HealthStepsRead, rows)] == [1, 2]
