from datetime import date, timedelta


class TestGetStartDateForInterval:
    def test_last_30_days(self):
        from modules.health.utils import get_start_date_for_interval

        result = get_start_date_for_interval("last_30_days")
        assert result == date.today() - timedelta(days=30)

    def test_last_90_days(self):
        from modules.health.utils import get_start_date_for_interval

        result = get_start_date_for_interval("last_90_days")
        assert result == date.today() - timedelta(days=90)

    def test_last_year(self):
        from modules.health.utils import get_start_date_for_interval

        result = get_start_date_for_interval("last_year")
        assert result == date.today() - timedelta(days=365)

    def test_all_time(self):
        from modules.health.utils import get_start_date_for_interval

        result = get_start_date_for_interval("all_time")
        assert result == date.min

    def test_default(self):
        from modules.health.utils import get_start_date_for_interval

        result = get_start_date_for_interval("unknown")
        assert result == date.today() - timedelta(days=7)


class TestIntervalEnum:
    def test_values(self):
        from modules.health.constants import Interval

        assert Interval.LAST_7_DAYS.value == "last_7_days"
        assert Interval.LAST_30_DAYS.value == "last_30_days"
        assert Interval.LAST_90_DAYS.value == "last_90_days"
        assert Interval.LAST_YEAR.value == "last_year"
        assert Interval.ALL_TIME.value == "all_time"
