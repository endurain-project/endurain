"""Tests for streak settings API endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import users.users_streak_settings.router as streak_settings_router
import users.users_streak_settings.schema as streak_settings_schema


@pytest.fixture
def client(fast_api_app) -> TestClient:
    """Mount the streak settings router on the shared test app as user 1."""
    fast_api_app.include_router(streak_settings_router.router, prefix="/profile/streak_settings")
    fast_api_app.state.mock_user_id = 1
    return TestClient(fast_api_app)


class TestStreakSettingsRouter:
    @patch("users.users_streak_settings.router.streak_settings_crud.get_streak_settings_by_user_id")
    def test_read(self, mock_get, client):
        """Returns the stored settings for the authenticated user."""
        mock_get.return_value = streak_settings_schema.UsersStreakSettingsRead(user_id=1, min_activities_per_week=2)

        response = client.get("/profile/streak_settings")

        assert response.status_code == 200
        assert response.json() == {
            "user_id": 1,
            "min_activities_per_week": 2,
            "activity_types": None,
            "show_on_profile": False,
        }
        assert mock_get.call_args.args[0] == 1

    @patch("users.users_streak_settings.router.streak_settings_crud.upsert_streak_settings")
    def test_update(self, mock_upsert, client):
        """Passes the validated payload and user ID to the upsert."""
        mock_upsert.return_value = streak_settings_schema.UsersStreakSettingsRead(
            user_id=1, min_activities_per_week=3, activity_types=[1], show_on_profile=True
        )

        response = client.put(
            "/profile/streak_settings",
            json={"min_activities_per_week": 3, "activity_types": [1], "show_on_profile": True},
        )

        assert response.status_code == 200
        assert response.json()["activity_types"] == [1]
        user_id, payload, _db = mock_upsert.call_args.args
        assert user_id == 1
        assert payload.min_activities_per_week == 3

    def test_update_invalid(self, client):
        """Rejects an out-of-range weekly target with 422."""
        response = client.put("/profile/streak_settings", json={"min_activities_per_week": 0})
        assert response.status_code == 422
