"""Tests for the weekly streak service."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import modules.users.users_streak_settings.schema as streak_settings_schema
import modules.users.users_streaks.service as streak_service

# Wednesday 2026-10-14; the Monday-based week starts 2026-10-12.
TODAY = date(2026, 10, 14)


def _activity(start: datetime | None, tz: str | None = "Europe/Zurich") -> SimpleNamespace:
    """Build an activity start reference with the fields the service reads."""
    return SimpleNamespace(start_time=start, timezone=tz)


def _settings(**kwargs) -> streak_settings_schema.UsersStreakSettingsBase:
    """Build streak settings with the given overrides."""
    return streak_settings_schema.UsersStreakSettingsBase(**kwargs)


@patch("modules.users.users_streaks.service.activity_integration.list_user_activity_starts")
class TestGetWeeklyStreak:
    def test_counts_weeks_and_targets(self, mock_list):
        """Counts local-date weeks and applies the weekly target."""
        mock_list.return_value = [
            # Current week (Mon 12 Oct)
            _activity(datetime(2026, 10, 13, 7, tzinfo=UTC)),
            # Sunday 22:30 UTC is already Monday in Zurich -> current week
            _activity(datetime(2026, 10, 11, 22, 30, tzinfo=UTC)),
            # Last week proper
            _activity(datetime(2026, 10, 6, 7, tzinfo=UTC)),
            # Two weeks ago
            _activity(datetime(2026, 9, 29, 7, tzinfo=UTC)),
            # No start time
            _activity(None),
        ]
        db = MagicMock()

        all_types = streak_service.get_weekly_streak(1, "monday", _settings(), TODAY, db)
        assert all_types.current_week_start == date(2026, 10, 12)
        assert all_types.current_week_count == 2
        assert all_types.current_streak == 3
        assert all_types.current_streak_start == date(2026, 9, 28)
        mock_list.assert_called_with(1, db, activity_types=None)

        two_per_week = streak_service.get_weekly_streak(1, "monday", _settings(min_activities_per_week=2), TODAY, db)
        assert two_per_week.current_streak == 1
        assert two_per_week.current_week_met is True
        assert two_per_week.min_activities_per_week == 2

    def test_passes_activity_type_filter(self, mock_list):
        """Hands the configured activity types to the query and echoes them back."""
        mock_list.return_value = []
        db = MagicMock()

        runs_only = streak_service.get_weekly_streak(1, "monday", _settings(activity_types=[1]), TODAY, db)

        mock_list.assert_called_once_with(1, db, activity_types=[1])
        assert runs_only.activity_types == [1]

    def test_follows_first_day_of_week(self, mock_list):
        """Buckets a Sunday activity into a different week depending on the first weekday."""
        # Sunday 11 Oct 10:00 local time
        mock_list.return_value = [_activity(datetime(2026, 10, 11, 8, tzinfo=UTC))]

        monday = streak_service.get_weekly_streak(1, "monday", _settings(), TODAY, MagicMock())
        assert monday.current_week_start == date(2026, 10, 12)
        assert monday.current_week_count == 0
        assert monday.recent_weeks[-2].week_start == date(2026, 10, 5)
        assert monday.recent_weeks[-2].activity_count == 1

        sunday = streak_service.get_weekly_streak(1, "sunday", _settings(), TODAY, MagicMock())
        assert sunday.current_week_start == date(2026, 10, 11)
        assert sunday.current_week_count == 1
        assert sunday.current_week_met is True

    def test_no_activities(self, mock_list):
        """Returns an empty streak with a full history strip when there are no activities."""
        mock_list.return_value = []

        result = streak_service.get_weekly_streak(1, "sunday", _settings(), TODAY, MagicMock())

        assert result.current_streak == 0
        assert result.longest_streak == 0
        assert result.current_week_start == date(2026, 10, 11)
        assert len(result.recent_weeks) == 12
