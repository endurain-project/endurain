"""Tests for the pure weekly streak helpers."""

from datetime import UTC, date, datetime, timedelta

import activities.activity_streaks.utils as streak_utils

# 2026-10-12 is a Monday.
THIS_WEEK = date(2026, 10, 12)


def _weeks_ago(n: int) -> date:
    return THIS_WEEK - timedelta(weeks=n)


class TestLocalStartDate:
    def test_converts_to_activity_timezone(self):
        # 23:30 UTC on Sunday is already Monday in Zurich.
        start = datetime(2026, 10, 11, 23, 30, tzinfo=UTC)
        assert streak_utils.local_start_date(start, "Europe/Zurich") == date(2026, 10, 12)

    def test_naive_is_treated_as_utc(self):
        assert streak_utils.local_start_date(datetime(2026, 10, 11, 23, 30), None) == date(2026, 10, 11)

    def test_prefixed_timezone_string(self):
        start = datetime(2026, 10, 11, 23, 30, tzinfo=UTC)
        assert streak_utils.local_start_date(start, "(GMT+01:00) Europe/Zurich") == date(2026, 10, 12)

    def test_unknown_timezone_falls_back_to_utc(self):
        start = datetime(2026, 10, 11, 23, 30, tzinfo=UTC)
        assert streak_utils.local_start_date(start, "Not/AZone") == date(2026, 10, 11)

    def test_none_start_time(self):
        assert streak_utils.local_start_date(None, "UTC") is None  # type: ignore[arg-type]


class TestTodayForTimezone:
    def test_uses_timezone(self):
        now = datetime(2026, 10, 11, 23, 30, tzinfo=UTC)
        assert streak_utils.today_for_timezone("Europe/Zurich", now) == date(2026, 10, 12)
        assert streak_utils.today_for_timezone(None, now) == date(2026, 10, 11)


class TestBucketActivitiesByWeek:
    def test_monday_weeks(self):
        dates = [date(2026, 10, 12), date(2026, 10, 18), date(2026, 10, 11)]
        counts = streak_utils.bucket_activities_by_week(dates, "monday")
        assert counts == {date(2026, 10, 12): 2, date(2026, 10, 5): 1}

    def test_sunday_weeks(self):
        dates = [date(2026, 10, 11), date(2026, 10, 17), date(2026, 10, 18)]
        counts = streak_utils.bucket_activities_by_week(dates, "sunday")
        assert counts == {date(2026, 10, 11): 2, date(2026, 10, 18): 1}


class TestCalculateWeeklyStreak:
    def test_no_activities(self):
        result = streak_utils.calculate_weekly_streak({}, THIS_WEEK, 1)
        assert result.current_streak == 0
        assert result.longest_streak == 0
        assert result.current_streak_start is None
        assert result.longest_streak_start is None
        assert result.at_risk is False
        assert result.current_week_met is False
        assert len(result.recent_weeks) == streak_utils.DEFAULT_RECENT_WEEKS
        assert result.recent_weeks[-1] == (THIS_WEEK, 0, False)
        assert result.recent_weeks[0][0] == _weeks_ago(11)

    def test_current_week_met_extends_streak(self):
        counts = {THIS_WEEK: 1, _weeks_ago(1): 2, _weeks_ago(2): 1}
        result = streak_utils.calculate_weekly_streak(counts, THIS_WEEK, 1)
        assert result.current_streak == 3
        assert result.current_streak_start == _weeks_ago(2)
        assert result.current_week_met is True
        assert result.at_risk is False

    def test_current_week_in_progress_does_not_break_streak(self):
        counts = {_weeks_ago(1): 1, _weeks_ago(2): 1}
        result = streak_utils.calculate_weekly_streak(counts, THIS_WEEK, 1)
        assert result.current_streak == 2
        assert result.at_risk is True
        assert result.current_week_count == 0

    def test_gap_last_week_resets_streak(self):
        counts = {_weeks_ago(2): 1, _weeks_ago(3): 1}
        result = streak_utils.calculate_weekly_streak(counts, THIS_WEEK, 1)
        assert result.current_streak == 0
        assert result.at_risk is False
        assert result.longest_streak == 2

    def test_min_activities_threshold(self):
        counts = {THIS_WEEK: 2, _weeks_ago(1): 3, _weeks_ago(2): 2, _weeks_ago(3): 3}
        result = streak_utils.calculate_weekly_streak(counts, THIS_WEEK, 3)
        assert result.current_streak == 1
        assert result.current_streak_start == _weeks_ago(1)
        assert result.at_risk is True
        assert result.current_week_count == 2
        assert result.longest_streak == 1
        # Most recent run wins ties.
        assert result.longest_streak_start == _weeks_ago(1)
        assert [met for _, _, met in result.recent_weeks[-4:]] == [True, False, True, False]

    def test_longest_streak_in_past(self):
        counts = {_weeks_ago(n): 1 for n in range(10, 15)}
        counts[THIS_WEEK] = 1
        result = streak_utils.calculate_weekly_streak(counts, THIS_WEEK, 1)
        assert result.current_streak == 1
        assert result.longest_streak == 5
        assert result.longest_streak_start == _weeks_ago(14)
        assert result.longest_streak_end == _weeks_ago(10)

    def test_future_weeks_ignored(self):
        counts = {THIS_WEEK + timedelta(weeks=1): 5}
        result = streak_utils.calculate_weekly_streak(counts, THIS_WEEK, 1)
        assert result.current_streak == 0
        assert result.longest_streak == 0

    def test_zero_target_is_clamped_to_one(self):
        result = streak_utils.calculate_weekly_streak({}, THIS_WEEK, 0)
        assert result.current_streak == 0
        assert result.recent_weeks[-1] == (THIS_WEEK, 0, False)

    def test_custom_history_length(self):
        result = streak_utils.calculate_weekly_streak({}, THIS_WEEK, 1, recent_weeks=4)
        assert [week for week, _, _ in result.recent_weeks] == [_weeks_ago(n) for n in (3, 2, 1, 0)]
