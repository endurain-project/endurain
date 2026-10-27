"""Tests for the aggregated user-profile overview."""

from types import SimpleNamespace
from unittest.mock import patch

import modules.activities.activity.schema as activity_schema
import modules.followers.contracts as followers_contracts
import modules.users.users.schema as users_schema
import modules.users.users_profile.service as profile_service


def test_overview_assembles_public_profile_and_summary_data(mock_db):
    user = users_schema.UserPublicRead(id=7, name="Ada", username="ada", city="Lisbon")
    week_stats = activity_schema.ActivityStatsRead()
    month_stats = activity_schema.ActivityStatsRead()
    activity_summary = SimpleNamespace(week_stats=week_stats, month_stats=month_stats, month_activity_count=4)
    follow_counts = followers_contracts.ProfileFollowCounts(followers=12, following=8)

    with (
        patch.object(profile_service.users_integration, "get_public_profile", return_value=user) as get_user,
        patch.object(
            profile_service.activities_integration, "get_user_profile_summary", return_value=activity_summary
        ) as stats,
        patch.object(
            profile_service.followers_integration, "get_profile_follow_counts", return_value=follow_counts
        ) as counts,
    ):
        overview = profile_service.get_user_profile_overview(7, 3, mock_db, anchor_date=None)

    get_user.assert_called_once_with(7, mock_db)
    stats.assert_called_once_with(7, 3, mock_db, anchor=None)
    counts.assert_called_once_with(7, 3, mock_db)
    assert overview.user == user
    assert overview.week_stats == week_stats
    assert overview.month_stats == month_stats
    assert overview.month_activity_count == 4
    assert overview.followers_count == 12
    assert overview.following_count == 8


def test_overview_keeps_profile_available_when_follow_network_is_private(mock_db):
    user = users_schema.UserPublicRead(id=7, name="Ada", username="ada")
    week_stats = activity_schema.ActivityStatsRead()
    month_stats = activity_schema.ActivityStatsRead()
    activity_summary = SimpleNamespace(week_stats=week_stats, month_stats=month_stats, month_activity_count=4)

    with (
        patch.object(profile_service.users_integration, "get_public_profile", return_value=user),
        patch.object(profile_service.activities_integration, "get_user_profile_summary", return_value=activity_summary),
        patch.object(profile_service.followers_integration, "get_profile_follow_counts", return_value=None),
    ):
        overview = profile_service.get_user_profile_overview(7, 3, mock_db, anchor_date=None)

    assert overview.user == user
    assert overview.followers_count is None
    assert overview.following_count is None
