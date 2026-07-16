from datetime import date, timedelta
from unittest.mock import patch


class TestCalculateStreaks:
    def test_no_completed_fasts(self, mock_db):
        from modules.health.health_fasting.utils import calculate_streaks

        with patch(
            "modules.health.health_fasting.utils.health_fasting_crud.get_completed_fasting_dates_by_user_id"
        ) as m:
            m.return_value = []
            current, longest = calculate_streaks(1, mock_db)
            assert current == 0
            assert longest == 0

    def test_empty_dates_list(self, mock_db):
        from modules.health.health_fasting.utils import calculate_streaks

        with patch(
            "modules.health.health_fasting.utils.health_fasting_crud.get_completed_fasting_dates_by_user_id"
        ) as m:
            m.return_value = []
            current, longest = calculate_streaks(1, mock_db)
            assert current == 0
            assert longest == 0

    def test_single_day(self, mock_db):
        from modules.health.health_fasting.utils import calculate_streaks

        with patch(
            "modules.health.health_fasting.utils.health_fasting_crud.get_completed_fasting_dates_by_user_id"
        ) as m:
            m.return_value = [date(2024, 1, 15)]
            current, longest = calculate_streaks(1, mock_db)
            assert current == 0  # not today or yesterday
            assert longest == 1

    def test_consecutive_days(self, mock_db):
        from modules.health.health_fasting.utils import calculate_streaks

        today = date.today()
        dates = [
            today - timedelta(days=2),
            today - timedelta(days=1),
            today,
        ]

        with patch(
            "modules.health.health_fasting.utils.health_fasting_crud.get_completed_fasting_dates_by_user_id"
        ) as m:
            m.return_value = dates
            current, longest = calculate_streaks(1, mock_db)
            assert current == 3
            assert longest == 3

    def test_current_streak_active_yesterday(self, mock_db):
        from modules.health.health_fasting.utils import calculate_streaks

        today = date.today()
        dates = [
            today - timedelta(days=3),
            today - timedelta(days=2),
            today - timedelta(days=1),
        ]

        with patch(
            "modules.health.health_fasting.utils.health_fasting_crud.get_completed_fasting_dates_by_user_id"
        ) as m:
            m.return_value = dates
            current, longest = calculate_streaks(1, mock_db)
            assert current == 3
            assert longest == 3

    def test_broken_streak(self, mock_db):
        from modules.health.health_fasting.utils import calculate_streaks

        today = date.today()
        dates = [
            today - timedelta(days=5),
            today - timedelta(days=4),
            today - timedelta(days=2),
            today - timedelta(days=1),
        ]

        with patch(
            "modules.health.health_fasting.utils.health_fasting_crud.get_completed_fasting_dates_by_user_id"
        ) as m:
            m.return_value = dates
            current, longest = calculate_streaks(1, mock_db)
            assert current == 2  # last 2 days
            assert longest == 2  # both streaks are length 2

    def test_not_current_streak(self, mock_db):
        from modules.health.health_fasting.utils import calculate_streaks

        today = date.today()
        dates = [
            today - timedelta(days=4),
            today - timedelta(days=3),
            today - timedelta(days=2),
        ]

        with patch(
            "modules.health.health_fasting.utils.health_fasting_crud.get_completed_fasting_dates_by_user_id"
        ) as m:
            m.return_value = dates
            current, longest = calculate_streaks(1, mock_db)
            assert current == 0  # last fast was 2 days ago
            assert longest == 3
