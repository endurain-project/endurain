"""Tests for the activities read/stats/feed service orchestration."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


class TestGetActivitiesInTimeframe:
    @patch("modules.activities.activity.service.activities_crud")
    def test_owner_gets_all(self, mock_crud):
        from modules.activities.activity import service

        db = MagicMock()
        service.get_activities_in_timeframe(1, "s", "e", 1, db)
        # Owner path: is_owner=True, no requester scoping.
        mock_crud.get_user_activities_per_timeframe.assert_called_once_with(1, "s", "e", db, True)

    @patch("modules.activities.activity.service.activities_crud")
    def test_requester_gets_visible(self, mock_crud):
        from modules.activities.activity import service

        db = MagicMock()
        service.get_activities_in_timeframe(1, "s", "e", 2, db)
        # Non-owner path: is_owner=False + requester scoping for the visibility mask.
        mock_crud.get_user_activities_per_timeframe.assert_called_once_with(1, "s", "e", db, False, requester_user_id=2)


class TestListWeekActivities:
    @patch("modules.activities.activity.service.get_activities_in_timeframe")
    def test_delegates_with_bounds(self, mock_get):
        from modules.activities.activity import service

        mock_get.return_value = ["a"]
        result = service.list_week_activities(3, 0, 3, MagicMock())
        assert result == ["a"]
        # user_id (arg 0) and requester_user_id (arg 3) are threaded through.
        assert mock_get.call_args.args[0] == 3
        assert mock_get.call_args.args[3] == 3


class TestPeriodStats:
    @patch("modules.activities.activity.service.activities_stats.calculate_activity_stats", return_value="stats")
    @patch("modules.activities.activity.service.get_activities_in_timeframe", return_value=[MagicMock()])
    def test_week_stats_with_activities(self, mock_get, mock_calc):
        from modules.activities.activity import service

        assert service.week_stats(1, 1, MagicMock()) == "stats"
        mock_calc.assert_called_once()

    @patch("modules.activities.activity.service.get_activities_in_timeframe", return_value=None)
    def test_week_stats_empty_returns_empty_stats(self, mock_get):
        import modules.activities.activity.schema as schema
        from modules.activities.activity import service

        assert isinstance(service.week_stats(1, 1, MagicMock()), schema.ActivityStats)

    @patch("modules.activities.activity.service.activities_stats.calculate_activity_stats", return_value="stats")
    @patch("modules.activities.activity.service.get_activities_in_timeframe", return_value=[MagicMock()])
    def test_month_stats_with_activities(self, mock_get, mock_calc):
        from modules.activities.activity import service

        assert service.month_stats(1, 1, MagicMock()) == "stats"

    @patch("modules.activities.activity.service.get_activities_in_timeframe", return_value=None)
    def test_month_stats_empty_returns_empty_stats(self, mock_get):
        import modules.activities.activity.schema as schema
        from modules.activities.activity import service

        assert isinstance(service.month_stats(1, 1, MagicMock()), schema.ActivityStats)

    @patch("modules.activities.activity.service.get_activities_in_timeframe", return_value=[MagicMock(), MagicMock()])
    def test_count_month_activities(self, mock_get):
        from modules.activities.activity import service

        assert service.count_month_activities(1, 1, MagicMock()) == 2

    @patch("modules.activities.activity.service.get_activities_in_timeframe", return_value=None)
    def test_count_month_activities_none(self, mock_get):
        from modules.activities.activity import service

        assert service.count_month_activities(1, 1, MagicMock()) == 0


class TestFollowingFeed:
    @patch("modules.activities.activity.service.activities_crud")
    def test_owner_gets_feed(self, mock_crud):
        from modules.activities.activity import service

        db = MagicMock()
        service.get_following_feed(1, 1, 2, 10, db)
        mock_crud.get_user_following_activities_with_pagination.assert_called_once_with(1, 2, 10, db)

    def test_feed_other_user_forbidden(self):
        from modules.activities.activity import service

        with pytest.raises(HTTPException) as exc:
            service.get_following_feed(2, 1, 1, 10, MagicMock())
        assert exc.value.status_code == 403

    @patch(
        "modules.activities.activity.service.activities_crud.count_user_following_activities",
        return_value=2,
    )
    def test_count_owner(self, mock_following):
        from modules.activities.activity import service

        assert service.count_following_feed(1, 1, MagicMock()) == 2

    def test_count_other_user_forbidden(self):
        from modules.activities.activity import service

        with pytest.raises(HTTPException) as exc:
            service.count_following_feed(2, 1, MagicMock())
        assert exc.value.status_code == 403


class TestListUserActivitiesPaginated:
    @patch("modules.activities.activity.service.activities_crud")
    def test_owner_scoping(self, mock_crud):
        from modules.activities.activity import service

        service.list_user_activities_paginated(1, 1, 1, 10, MagicMock(), activity_type=2)
        kwargs = mock_crud.get_user_activities_with_pagination.call_args.kwargs
        assert kwargs["user_is_owner"] is True
        assert kwargs["requester_user_id"] == 1
        assert kwargs["activity_type"] == 2

    @patch("modules.activities.activity.service.activities_crud")
    def test_non_owner_scoping(self, mock_crud):
        from modules.activities.activity import service

        service.list_user_activities_paginated(1, 2, 1, 10, MagicMock())
        kwargs = mock_crud.get_user_activities_with_pagination.call_args.kwargs
        assert kwargs["user_is_owner"] is False
        assert kwargs["requester_user_id"] == 2
