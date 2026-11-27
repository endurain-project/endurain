"""Tests for weekly streak API endpoints."""

from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import modules.users.users_streaks.router as streak_router
import modules.users.users_streaks.schema as streak_schema
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID


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
    """Mount the router under test on the shared test app as the mock user."""
    fast_api_app.include_router(streak_router.router, prefix="/activities_streaks")
    fast_api_app.state.mock_user_id = MOCK_USER_ID
    return TestClient(fast_api_app)


class TestReadMyWeeklyStreak:
    @patch("modules.users.users_streaks.router.streak_service.read_own_weekly_streak")
    def test_success(self, mock_read, client):
        """Returns the viewer's own streak."""
        mock_read.return_value = _response()

        response = client.get("/activities_streaks")

        assert response.status_code == 200
        body = response.json()
        assert body["current_streak"] == 3
        assert body["recent_weeks"][0]["week_start"] == "2026-10-12"
        assert mock_read.call_args.args[0] == MOCK_USER_ID


class TestReadUserWeeklyStreak:
    @patch("modules.users.users_streaks.router.streak_service.read_profile_weekly_streak")
    def test_shared(self, mock_read, client):
        """Returns another user's streak with the viewer's id."""
        mock_read.return_value = _response()

        response = client.get(f"/activities_streaks/user/{OTHER_USER_ID}")

        assert response.status_code == 200
        assert response.json()["longest_streak"] == 5
        user_id, viewer_id, _db = mock_read.call_args.args
        assert user_id == OTHER_USER_ID
        assert viewer_id == MOCK_USER_ID

    @patch("modules.users.users_streaks.router.streak_service.read_profile_weekly_streak")
    def test_not_shared(self, mock_read, client):
        """Returns null when the service hides the streak."""
        mock_read.return_value = None

        response = client.get(f"/activities_streaks/user/{OTHER_USER_ID}")

        assert response.status_code == 200
        assert response.json() is None

    def test_invalid_user_id(self, client):
        """Rejects user IDs that are not UUIDs."""
        response = client.get("/activities_streaks/user/not-a-uuid")
        assert response.status_code == 422
