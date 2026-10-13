"""Tests for weekly streak API endpoints."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import activities.activity_streaks.router as streak_router
import activities.activity_streaks.schema as streak_schema
import users.users_streak_settings.schema as streak_settings_schema


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
    return user


class TestReadMyWeeklyStreak:
    @patch("activities.activity_streaks.router.streak_crud.get_weekly_streak")
    @patch("activities.activity_streaks.router.streak_settings_crud.get_streak_settings_by_user_id")
    @patch("activities.activity_streaks.router.users_utils.get_user_by_id_or_404")
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
        assert mock_streak.call_args.kwargs["user_id"] == 1
        assert mock_streak.call_args.kwargs["first_day_of_week"] == "monday"


class TestReadUserWeeklyStreak:
    @patch("activities.activity_streaks.router.streak_crud.get_weekly_streak")
    @patch("activities.activity_streaks.router.streak_settings_crud.get_streak_settings_by_user_id")
    @patch("activities.activity_streaks.router.users_utils.get_user_by_id_or_404")
    def test_other_user_shared(self, mock_user, mock_settings, mock_streak, client):
        """Returns another user's streak when they show it on their profile."""
        mock_user.return_value = _user()
        mock_settings.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=2, show_on_profile=True)
        mock_streak.return_value = _response()

        response = client.get("/activities_streaks/user/2")

        assert response.status_code == 200
        assert response.json()["longest_streak"] == 5
        assert mock_streak.call_args.kwargs["user_id"] == 2

    @patch("activities.activity_streaks.router.streak_crud.get_weekly_streak")
    @patch("activities.activity_streaks.router.streak_settings_crud.get_streak_settings_by_user_id")
    def test_other_user_not_shared(self, mock_settings, mock_streak, client):
        """Returns null without calculating when the owner keeps the streak private."""
        mock_settings.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=2)

        response = client.get("/activities_streaks/user/2")

        assert response.status_code == 200
        assert response.json() is None
        mock_streak.assert_not_called()

    @patch("activities.activity_streaks.router.streak_crud.get_weekly_streak")
    @patch("activities.activity_streaks.router.streak_settings_crud.get_streak_settings_by_user_id")
    @patch("activities.activity_streaks.router.users_utils.get_user_by_id_or_404")
    def test_own_profile_always_visible(self, mock_user, mock_settings, mock_streak, client):
        """Always returns the viewer's own streak, even when not shared."""
        mock_user.return_value = _user()
        mock_settings.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=1)
        mock_streak.return_value = _response()

        response = client.get("/activities_streaks/user/1")

        assert response.status_code == 200
        assert response.json()["current_streak"] == 3

    def test_invalid_user_id(self, client):
        """Rejects non-positive user IDs."""
        response = client.get("/activities_streaks/user/0")
        assert response.status_code in (400, 422)
