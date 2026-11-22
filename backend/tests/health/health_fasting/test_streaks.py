from datetime import date, timedelta

import pytest

import modules.health.health_fasting.streaks as health_fasting_streaks

_TODAY = date(2024, 1, 15)


def _days_ago(*offsets: int) -> list[date]:
    return [_TODAY - timedelta(days=offset) for offset in offsets]


class TestCalculateStreaks:
    def test_no_completed_fasts(self):
        assert health_fasting_streaks.calculate_streaks([], _TODAY) == (0, 0)

    def test_single_old_day_is_not_current(self):
        assert health_fasting_streaks.calculate_streaks(_days_ago(10), _TODAY) == (0, 1)

    @pytest.mark.parametrize(
        "offsets",
        [(2, 1, 0), (3, 2, 1)],
        ids=["ending today", "ending yesterday"],
    )
    def test_consecutive_run_ending_today_or_yesterday_is_current(self, offsets):
        assert health_fasting_streaks.calculate_streaks(_days_ago(*offsets), _TODAY) == (3, 3)

    def test_broken_run_keeps_the_longest_and_the_latest(self):
        assert health_fasting_streaks.calculate_streaks(_days_ago(5, 4, 2, 1), _TODAY) == (2, 2)

    def test_longest_run_can_be_older_than_the_current_one(self):
        assert health_fasting_streaks.calculate_streaks(_days_ago(9, 8, 7, 6, 1), _TODAY) == (1, 4)

    def test_run_that_ended_two_days_ago_is_not_current(self):
        assert health_fasting_streaks.calculate_streaks(_days_ago(4, 3, 2), _TODAY) == (0, 3)
