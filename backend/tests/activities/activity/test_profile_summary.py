"""Tests for the activity values aggregated for a user's profile."""

from datetime import date, datetime
from unittest.mock import patch

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service


def test_profile_summary_uses_visible_month_count_and_both_period_stats(mock_db):
    week_stats = activity_schema.ActivityStatsRead()
    month_stats = activity_schema.ActivityStatsRead()
    month_start = datetime(2026, 10, 1)
    month_end = datetime(2026, 10, 31)
    with (
        patch.object(activity_service, "_month_bounds", return_value=(month_start, month_end)),
        patch.object(activity_service, "_followees_of", return_value=[7]) as followees,
        patch.object(activity_service, "week_stats", return_value=week_stats) as week,
        patch.object(activity_service, "month_stats", return_value=month_stats) as month,
        patch.object(activity_service.activity_crud, "count_user_activities", return_value=4) as count,
    ):
        result = activity_service.user_profile_summary(7, 3, mock_db, anchor=date(2026, 10, 27))

    assert result == activity_contracts.UserProfileActivitySummary(week_stats, month_stats, 4)
    followees.assert_called_once_with(3, mock_db)
    count.assert_called_once_with(
        user_id=7,
        db=mock_db,
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 31),
        user_is_owner=False,
        followee_ids=[7],
    )
    week.assert_called_once_with(7, 3, mock_db, anchor=date(2026, 10, 27))
    month.assert_called_once_with(7, 3, mock_db, anchor=date(2026, 10, 27))


def test_profile_summary_resolves_the_requesters_today_once_when_no_anchor_is_given(mock_db):
    with (
        patch.object(activity_service.users_integration, "local_today", return_value=date(2026, 10, 27)) as today,
        patch.object(activity_service, "_followees_of", return_value=[]),
        patch.object(activity_service, "week_stats") as week,
        patch.object(activity_service, "month_stats") as month,
        patch.object(activity_service.activity_crud, "count_user_activities", return_value=0),
    ):
        activity_service.user_profile_summary(3, 3, mock_db)

    today.assert_called_once_with(3, mock_db)
    week.assert_called_once_with(3, 3, mock_db, anchor=date(2026, 10, 27))
    month.assert_called_once_with(3, 3, mock_db, anchor=date(2026, 10, 27))
