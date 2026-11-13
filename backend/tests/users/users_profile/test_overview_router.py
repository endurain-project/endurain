"""Tests for the aggregated user-profile overview route."""

import uuid
from datetime import date
from unittest.mock import ANY, patch

from tests._helpers.auth import MOCK_USER_ID

import modules.users.users_profile.schema as profile_schema

_USER_ID = uuid.UUID(int=1)

PREFIX = f"/api/v1/users/{_USER_ID}/overview"


def test_overview_route_returns_the_composed_profile(profile_client):
    expected = profile_schema.UserProfileOverviewRead(
        user={"id": str(_USER_ID), "name": "Ada", "username": "ada"},
        week_stats={},
        month_stats={},
        month_activity_count=4,
        followers_count=12,
        following_count=8,
    )
    with patch("modules.users.users_profile.overview_router.profile_service.get_user_profile_overview") as overview:
        overview.return_value = expected

        response = profile_client.get(PREFIX, params={"date": "2026-10-27"})

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "ada"
    assert response.json()["month_activity_count"] == 4
    overview.assert_called_once_with(_USER_ID, MOCK_USER_ID, ANY, anchor_date=date(2026, 10, 27))
