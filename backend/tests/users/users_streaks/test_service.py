"""Tests for the weekly streak service."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.users.users_streak_settings.schema as streak_settings_schema
import modules.users.users_streaks.service as streak_service
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

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

        all_types = streak_service.get_weekly_streak(MOCK_USER_ID, "monday", _settings(), TODAY, db, user_is_owner=True)
        assert all_types.current_week_start == date(2026, 10, 12)
        assert all_types.current_week_count == 2
        assert all_types.current_streak == 3
        assert all_types.current_streak_start == date(2026, 9, 28)
        mock_list.assert_called_with(MOCK_USER_ID, db, activity_types=None, user_is_owner=True)

        two_per_week = streak_service.get_weekly_streak(
            MOCK_USER_ID, "monday", _settings(min_activities_per_week=2), TODAY, db, user_is_owner=True
        )
        assert two_per_week.current_streak == 1
        assert two_per_week.current_week_met is True
        assert two_per_week.min_activities_per_week == 2

    def test_passes_activity_type_filter(self, mock_list):
        """Hands the configured activity types to the query and echoes them back."""
        mock_list.return_value = []
        db = MagicMock()

        runs_only = streak_service.get_weekly_streak(
            MOCK_USER_ID, "monday", _settings(activity_types=[1]), TODAY, db, user_is_owner=False
        )

        mock_list.assert_called_once_with(MOCK_USER_ID, db, activity_types=[1], user_is_owner=False)
        assert runs_only.activity_types == [1]

    def test_follows_first_day_of_week(self, mock_list):
        """Buckets a Sunday activity into a different week depending on the first weekday."""
        # Sunday 11 Oct 10:00 local time
        mock_list.return_value = [_activity(datetime(2026, 10, 11, 8, tzinfo=UTC))]

        monday = streak_service.get_weekly_streak(
            MOCK_USER_ID, "monday", _settings(), TODAY, MagicMock(), user_is_owner=True
        )
        assert monday.current_week_start == date(2026, 10, 12)
        assert monday.current_week_count == 0
        assert monday.recent_weeks[-2].week_start == date(2026, 10, 5)
        assert monday.recent_weeks[-2].activity_count == 1

        sunday = streak_service.get_weekly_streak(
            MOCK_USER_ID, "sunday", _settings(), TODAY, MagicMock(), user_is_owner=True
        )
        assert sunday.current_week_start == date(2026, 10, 11)
        assert sunday.current_week_count == 1
        assert sunday.current_week_met is True

    def test_no_activities(self, mock_list):
        """Returns an empty streak with a full history strip when there are no activities."""
        mock_list.return_value = []

        result = streak_service.get_weekly_streak(
            MOCK_USER_ID, "sunday", _settings(), TODAY, MagicMock(), user_is_owner=True
        )

        assert result.current_streak == 0
        assert result.longest_streak == 0
        assert result.current_week_start == date(2026, 10, 11)
        assert len(result.recent_weeks) == 12


def _user(timezone: str | None = "Europe/Zurich") -> SimpleNamespace:
    """Build a user record with the fields the service reads."""
    return SimpleNamespace(first_day_of_week="sunday", timezone=timezone)


@patch("modules.users.users_streaks.service.get_weekly_streak")
@patch("modules.users.users_streaks.service.streak_settings_integration.get_streak_settings")
@patch("modules.users.users_streaks.service.users_integration.get_user")
class TestReadWeeklyStreak:
    def test_own_streak_uses_the_users_week_and_timezone(self, mock_user, mock_settings, mock_streak):
        """Calculates the owner's streak with their first weekday and today in their timezone."""
        db = MagicMock()
        mock_user.return_value = _user()
        settings = streak_settings_schema.UsersStreakSettingsRead(user_id=MOCK_USER_ID)
        mock_settings.return_value = settings

        with patch("modules.users.users_streaks.service.core_timezone.today_in", return_value=TODAY) as mock_today:
            result = streak_service.read_own_weekly_streak(MOCK_USER_ID, db)

        assert result is mock_streak.return_value
        mock_today.assert_called_once_with("Europe/Zurich")
        mock_streak.assert_called_once_with(MOCK_USER_ID, "sunday", settings, TODAY, db, user_is_owner=True)

    def test_unknown_user(self, mock_user, mock_settings, mock_streak):
        """Raises not found when the user does not exist."""
        mock_user.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            streak_service.read_own_weekly_streak(MOCK_USER_ID, MagicMock())
        mock_streak.assert_not_called()

    def test_profile_hidden_from_others_unless_shared(self, mock_user, mock_settings, mock_streak):
        """Returns None to another viewer when the owner keeps the streak private."""
        mock_settings.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=OTHER_USER_ID)

        assert streak_service.read_profile_weekly_streak(OTHER_USER_ID, MOCK_USER_ID, MagicMock()) is None
        mock_streak.assert_not_called()

    def test_profile_shared_with_others_excludes_owner_only_data(self, mock_user, mock_settings, mock_streak):
        """Calculates a shared streak for another viewer as a non-owner read."""
        mock_user.return_value = _user()
        mock_settings.return_value = streak_settings_schema.UsersStreakSettingsRead(
            user_id=OTHER_USER_ID, show_on_profile=True
        )

        result = streak_service.read_profile_weekly_streak(OTHER_USER_ID, MOCK_USER_ID, MagicMock())

        assert result is mock_streak.return_value
        assert mock_streak.call_args.kwargs == {"user_is_owner": False}

    def test_own_profile_always_visible(self, mock_user, mock_settings, mock_streak):
        """Returns the owner's streak on their own profile even when private."""
        mock_user.return_value = _user()
        mock_settings.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=MOCK_USER_ID)

        result = streak_service.read_profile_weekly_streak(MOCK_USER_ID, MOCK_USER_ID, MagicMock())

        assert result is mock_streak.return_value
        assert mock_streak.call_args.kwargs == {"user_is_owner": True}
