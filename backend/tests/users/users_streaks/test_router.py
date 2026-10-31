"""Tests for weekly streak API endpoints."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import modules.users.users_streak_settings.schema as streak_settings_schema
import modules.users.users_streaks.router as streak_router
import modules.users.users_streaks.schema as streak_schema


def _response() -> streak_schema.WeeklyStreakResponse:
    """Build a representative weekly streak response."""
    return streak_schema.WeeklyStreakResponse(
        current_streak=3,
        current_streak_start=date(2026, 9, 28),
        longest_streak=5,
        longest_streak_start=date(2026, 1, 5),
        longest_streak_end=date(2026, 2, 2),
        current_week_start=date(2026, 10, 12),
        current_week_count=1,
        current_week_met=True,
        at_risk=False,
        min_activities_per_week=1,
        activity_types=None,
        recent_weeks=[streak_schema.StreakWeek(week_start=date(2026, 10, 12), activity_count=1, met=True)],
    )


@pytest.fixture
def client(fast_api_app) -> TestClient:
    """Mount the router under test on the shared test app as user 1."""
    fast_api_app.include_router(streak_router.router, prefix="/activities_streaks")
    fast_api_app.state.mock_user_id = 1
    return TestClient(fast_api_app)


def _user() -> MagicMock:
    """Build a mock user whose week starts on Monday."""
    user = MagicMock()
    user.first_day_of_week = "monday"
    user.timezone = "Europe/Zurich"
    return user


class TestReadMyWeeklyStreak:
    @patch("modules.users.users_streaks.router.streak_service.get_weekly_streak")
    @patch("modules.users.users_streaks.router.streak_settings_crud.get_streak_settings_by_user_id")
    @patch("modules.users.users_streaks.router.users_utils.get_user_by_id_or_404")
    def test_success(self, mock_user, mock_settings, mock_streak, client):
        """Returns the viewer's own streak using their first day of week."""
        mock_user.return_value = _user()
        mock_settings.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=1)
        mock_streak.return_value = _response()

        response = client.get("/activities_streaks")

        assert response.status_code == 200
        body = response.json()
        assert body["current_streak"] == 3
        assert body["recent_weeks"][0]["week_start"] == "2026-10-12"
        user_id, first_day_of_week, _settings, _today, _db = mock_streak.call_args.args
        assert user_id == 1
        assert first_day_of_week == "monday"
        assert mock_streak.call_args.kwargs == {"user_is_owner": True}


class TestReadUserWeeklyStreak:
    @patch("modules.users.users_streaks.router.streak_service.get_weekly_streak")
    @patch("modules.users.users_streaks.router.streak_settings_crud.get_streak_settings_by_user_id")
    @patch("modules.users.users_streaks.router.users_utils.get_user_by_id_or_404")
    def test_other_user_shared(self, mock_user, mock_settings, mock_streak, client):
        """Returns another user's streak when they show it on their profile."""
        mock_user.return_value = _user()
        mock_settings.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=2, show_on_profile=True)
        mock_streak.return_value = _response()

        response = client.get("/activities_streaks/user/2")

        assert response.status_code == 200
        assert response.json()["longest_streak"] == 5
        assert mock_streak.call_args.args[0] == 2
        assert mock_streak.call_args.kwargs == {"user_is_owner": False}

    @patch("modules.users.users_streaks.router.streak_service.get_weekly_streak")
    @patch("modules.users.users_streaks.router.streak_settings_crud.get_streak_settings_by_user_id")
    def test_other_user_not_shared(self, mock_settings, mock_streak, client):
        """Returns null without calculating when the owner keeps the streak private."""
        mock_settings.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=2)

        response = client.get("/activities_streaks/user/2")

        assert response.status_code == 200
        assert response.json() is None
        mock_streak.assert_not_called()

    @patch("modules.users.users_streaks.router.streak_service.get_weekly_streak")
    @patch("modules.users.users_streaks.router.streak_settings_crud.get_streak_settings_by_user_id")
    @patch("modules.users.users_streaks.router.users_utils.get_user_by_id_or_404")
    def test_own_profile_always_visible(self, mock_user, mock_settings, mock_streak, client):
        """Always returns the viewer's own streak, even when not shared."""
        mock_user.return_value = _user()
        mock_settings.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=1)
        mock_streak.return_value = _response()

        response = client.get("/activities_streaks/user/1")

        assert response.status_code == 200
        assert response.json()["current_streak"] == 3
        assert mock_streak.call_args.kwargs == {"user_is_owner": True}

    def test_invalid_user_id(self, client):
        """Rejects non-positive user IDs."""
        response = client.get("/activities_streaks/user/0")
        assert response.status_code in (400, 422)
