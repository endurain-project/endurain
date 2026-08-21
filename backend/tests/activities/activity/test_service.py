"""Tests for the activities read/stats/feed service orchestration."""

from datetime import date
from unittest.mock import ANY, MagicMock, patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions

# A Thursday, so week bounds straddle a month boundary in neither direction.
_TODAY = date(2026, 3, 12)


@pytest.fixture(autouse=True)
def stub_user_local_today():
    """Pin "today".

    The service resolves the anchor in the *requester's* timezone, which is a DB
    read; without this the bounds tests would also drift with the wall clock.
    """
    with patch(
        "modules.activities.activity.service.users_integration_service.local_today",
        return_value=_TODAY,
    ) as mock:
        yield mock


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
        with patch(
            "modules.activities.activity.service.followers_integration.list_accepted_followee_ids",
            return_value=[1],
        ):
            service.get_activities_in_timeframe(1, "s", "e", 2, db)
        # Non-owner path: the service resolves the followees, the query filters on them.
        mock_crud.get_user_activities_per_timeframe.assert_called_once_with(1, "s", "e", db, False, followee_ids=[1])


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


class TestListUserActivitiesPaginated:
    @patch("modules.activities.activity.service.followers_integration.list_accepted_followee_ids", return_value=[])
    @patch("modules.activities.activity.service.activities_crud")
    def test_owner_scoping(self, mock_crud, _mock_followers):
        from modules.activities.activity import service

        service.list_user_activities_paginated(1, 1, 1, 10, MagicMock(), activity_type=2)
        kwargs = mock_crud.get_user_activities_with_pagination.call_args.kwargs
        assert kwargs["user_is_owner"] is True
        assert kwargs["activity_type"] == 2

    @patch("modules.activities.activity.service.followers_integration.list_accepted_followee_ids", return_value=[9])
    @patch("modules.activities.activity.service.activities_crud")
    def test_non_owner_scoping(self, mock_crud, _mock_followers):
        from modules.activities.activity import service

        service.list_user_activities_paginated(1, 2, 1, 10, MagicMock())
        kwargs = mock_crud.get_user_activities_with_pagination.call_args.kwargs
        assert kwargs["user_is_owner"] is False
        assert kwargs["followee_ids"] == [9]


class TestPeriodBounds:
    """Week/month windows must be real calendar boundaries, not rolling spans."""

    def test_week_bounds_are_midnight_aligned(self):
        import modules.activities.activity.service as service

        start, end = service._week_bounds(1, MagicMock())

        assert (start.hour, start.minute, start.second, start.microsecond) == (0, 0, 0, 0)
        assert (end.hour, end.minute, end.second, end.microsecond) == (0, 0, 0, 0)
        assert start.weekday() == 0  # Monday
        assert (end - start).days == 6  # inclusive Sunday

    def test_week_bounds_walk_back_whole_weeks(self):
        import modules.activities.activity.service as service

        this_week, _ = service._week_bounds(1, MagicMock())
        last_week, _ = service._week_bounds(1, MagicMock(), 1)

        assert (this_week - last_week).days == 7
        assert last_week.weekday() == 0

    def test_month_bounds_cover_the_whole_month(self):
        import calendar

        import modules.activities.activity.service as service

        start, end = service._month_bounds(1, MagicMock())

        assert start.day == 1
        assert (start.hour, start.minute, start.second, start.microsecond) == (0, 0, 0, 0)
        # An activity recorded at 00:05 on the 1st used to fall outside the
        # window because the bound carried the current time of day.
        assert (end.hour, end.minute, end.second, end.microsecond) == (0, 0, 0, 0)
        assert end.day == calendar.monthrange(start.year, start.month)[1]


class TestAnchoredPeriodBounds:
    """The caller supplies its local date so "this week/month" matches its calendar.

    The request carries no timezone, so the date has to come from somewhere: the
    client's own anchor when it sends one, otherwise the requester's configured
    timezone. The server's UTC date is a day behind for callers far east and a
    day ahead for callers far west, landing them in the neighbouring week or
    month at the edges.
    """

    def test_week_bounds_use_the_supplied_anchor(self):
        import modules.activities.activity.service as service

        # Thu 2026-01-01; the ISO week runs Mon 2025-12-29 .. Sun 2026-01-04.
        start, end = service._week_bounds(1, MagicMock(), 0, date(2026, 1, 1))

        assert start.date() == date(2025, 12, 29)
        assert end.date() == date(2026, 1, 4)

    def test_week_anchor_at_a_year_boundary_beats_the_server_clock(self):
        import modules.activities.activity.service as service

        # A caller at UTC+13 is already on Mon 2026-01-05 while the server's UTC
        # date is still Sun 2026-01-04; the anchor must win.
        anchored, _ = service._week_bounds(1, MagicMock(), 0, date(2026, 1, 5))
        server_side, _ = service._week_bounds(1, MagicMock(), 0, date(2026, 1, 4))

        assert anchored.date() == date(2026, 1, 5)
        assert server_side.date() == date(2025, 12, 29)

    def test_month_bounds_use_the_supplied_anchor(self):
        import modules.activities.activity.service as service

        start, end = service._month_bounds(1, MagicMock(), date(2026, 2, 17))

        assert start.date() == date(2026, 2, 1)
        assert end.date() == date(2026, 2, 28)

    def test_falls_back_to_the_requesters_timezone_when_no_anchor(self, stub_user_local_today):
        """No anchor must mean the requester's calendar, never the server's."""
        import modules.activities.activity.service as service

        db = MagicMock()
        start, end = service._week_bounds(7, db)

        stub_user_local_today.assert_called_once_with(7, db)
        # _TODAY is Thu 2026-03-12 -> Mon 2026-03-09 .. Sun 2026-03-15.
        assert start.date() == date(2026, 3, 9)
        assert end.date() == date(2026, 3, 15)
        assert start.tzinfo is not None

    def test_an_anchor_does_not_hit_the_database(self, stub_user_local_today):
        """The client's own date is authoritative; no need to resolve a timezone."""
        import modules.activities.activity.service as service

        service._week_bounds(1, MagicMock(), 0, date(2026, 1, 1))

        stub_user_local_today.assert_not_called()

    def test_period_stats_forwards_the_anchor(self):
        import modules.activities.activity.service as service

        with patch.object(service, "month_stats") as month_stats:
            service.period_stats(1, "month", 1, "db", date(2026, 2, 17))

        month_stats.assert_called_once_with(1, 1, "db", date(2026, 2, 17))


class TestEditPublishesUpdated:
    """An edit is a domain fact: without it consumers can only see create/delete."""

    @patch("modules.activities.activity.service.activity_event_publishers")
    @patch("modules.activities.activity.service.activities_crud")
    def test_single_edit_publishes_only_the_fields_the_client_sent(self, mock_crud, mock_publishers):
        import modules.activities.activity.schema as activities_schema
        from modules.activities.activity import service

        db = MagicMock()
        service.edit_activity(5, 1, activities_schema.ActivityEdit(name="Run"), db)

        mock_crud.edit_activity.assert_called_once_with(1, 5, ANY, db, commit=False)
        mock_publishers.publish_activity_updated.assert_called_once_with(5, 1, ["name"], db=db, commit=db.commit)

    @patch("modules.activities.activity.service.activity_event_publishers")
    @patch("modules.activities.activity.service.activities_crud")
    def test_single_edit_lets_the_publisher_own_the_commit(self, mock_crud, mock_publishers):
        """Staged, not committed, so the outbox row joins the same transaction."""
        import modules.activities.activity.schema as activities_schema
        from modules.activities.activity import service

        db = MagicMock()
        service.edit_activity(5, 1, activities_schema.ActivityEdit(name="Run"), db)

        db.commit.assert_not_called()

    @patch("modules.activities.activity.service.activity_event_publishers")
    @patch("modules.activities.activity.service.activities_crud")
    def test_bulk_edit_publishes_one_event_per_changed_row(self, mock_crud, mock_publishers):
        import modules.activities.activity.schema as activities_schema
        from modules.activities.activity import service

        db = MagicMock()
        mock_crud.edit_user_activities_visibility.return_value = [4, 5, 6]

        updated = service.bulk_edit_activities(1, activities_schema.ActivitiesBulkEdit(visibility=1), db)

        assert updated == 3
        mock_publishers.publish_activities_updated.assert_called_once_with(
            [4, 5, 6], 1, ["visibility"], db, db.commit, source="api:bulk_edit_activities"
        )

    @patch("modules.activities.activity.service.activity_event_publishers")
    @patch("modules.activities.activity.service.activities_crud")
    def test_a_stale_edit_rolls_back_and_publishes_nothing(self, mock_crud, mock_publishers):
        import modules.activities.activity.schema as activities_schema
        from modules.activities.activity import service

        db = MagicMock()
        mock_crud.edit_activity.side_effect = StaleDataError()

        with pytest.raises(core_exceptions.PreconditionFailedError):
            service.edit_activity(5, 1, activities_schema.ActivityEdit(name="Run"), db)

        db.rollback.assert_called_once()
        mock_publishers.publish_activity_updated.assert_not_called()


class TestCrossModuleWrites:
    """The writes other modules reach through ``integration_service``.

    They are arranged here, in the module's own application layer, rather than on
    the surface that publishes them: a write reached from another module must be
    staged, published and committed exactly as one reached from a route.
    """

    @patch("modules.activities.activity.service.activity_event_publishers")
    @patch("modules.activities.activity.service.activities_crud")
    def test_bulk_set_activities_gear_publishes_one_event_per_row(self, mock_crud, mock_publishers):
        """A provider re-gearing activities is a change consumers must be able to see."""
        from modules.activities.activity import service

        db = MagicMock()
        mock_crud.bulk_set_activities_gear_id.return_value = [7, 8]

        updated = service.bulk_set_activities_gear(3, {7: 10, 8: 10}, db, source="api:test")

        assert updated == 2
        # Staged (commit=False) so the updates and their events are atomic.
        mock_crud.bulk_set_activities_gear_id.assert_called_once_with(3, {7: 10, 8: 10}, db, commit=False)
        mock_publishers.publish_activities_updated.assert_called_once_with(
            [7, 8], 3, ["gear_id"], db, db.commit, source="api:test"
        )

    @patch("modules.activities.activity.service.activity_event_publishers")
    @patch("modules.activities.activity.service.activities_crud")
    def test_delete_all_strava_activities_publishes_cleanup_events(self, mock_crud, mock_publishers):
        from modules.activities.activity import service

        db = MagicMock()
        mock_crud.delete_all_strava_activities_for_user.return_value = [11, 12, 13, 14, 15]

        deleted = service.delete_all_strava_activities(3, db, source="api:test")

        assert deleted == 5
        mock_crud.delete_all_strava_activities_for_user.assert_called_once_with(3, db, commit=False)
        mock_publishers.publish_activities_deleted.assert_called_once_with(
            [11, 12, 13, 14, 15], 3, db, db.commit, source="api:test"
        )

    @patch("modules.activities.activity.service.activity_event_publishers")
    @patch("modules.activities.activity.service.activities_crud")
    def test_delete_all_activities_for_user_publishes_cleanup_events(self, mock_crud, mock_publishers):
        """Account deletion must emit activity.deleted so stored blobs are reclaimed."""
        from modules.activities.activity import service

        db = MagicMock()
        mock_crud.delete_all_activities_for_user.return_value = [1, 2]

        deleted = service.delete_all_activities_for_user(7, db, source="api:test")

        assert deleted == 2
        mock_crud.delete_all_activities_for_user.assert_called_once_with(7, db, commit=False)
        mock_publishers.publish_activities_deleted.assert_called_once_with([1, 2], 7, db, db.commit, source="api:test")
