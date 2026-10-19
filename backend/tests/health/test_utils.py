from datetime import date, timedelta


class TestGetStartDateForInterval:
    """Windows are measured from the athlete's own today, passed in by the caller.

    Reading the server clock here made every interval filter shift by a day for
    users east/west of the container's timezone.
    """

    ANCHOR = date(2026, 3, 15)

    def test_last_30_days(self):
        from modules.health.utils import get_start_date_for_interval

        assert get_start_date_for_interval("last_30_days", self.ANCHOR) == self.ANCHOR - timedelta(days=30)

    def test_last_90_days(self):
        from modules.health.utils import get_start_date_for_interval

        assert get_start_date_for_interval("last_90_days", self.ANCHOR) == self.ANCHOR - timedelta(days=90)

    def test_last_year(self):
        from modules.health.utils import get_start_date_for_interval

        assert get_start_date_for_interval("last_year", self.ANCHOR) == self.ANCHOR - timedelta(days=365)

    def test_all_time(self):
        from modules.health.utils import get_start_date_for_interval

        assert get_start_date_for_interval("all_time", self.ANCHOR) == date.min

    def test_default(self):
        from modules.health.utils import get_start_date_for_interval

        assert get_start_date_for_interval("unknown", self.ANCHOR) == self.ANCHOR - timedelta(days=7)

    def test_anchor_drives_the_window_not_the_server_clock(self):
        """Two callers on different calendar days get different windows."""
        from modules.health.utils import get_start_date_for_interval

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
