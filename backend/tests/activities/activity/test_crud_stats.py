"""The per-type stats sums run in the database, so they run against a real session."""

from datetime import UTC, datetime

import pytest
from tests._helpers.db import create_sqlite_session

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud

_PRIVACY_FLAGS = (
    "hide_start_time",
    "hide_location",
    "hide_map",
    "hide_hr",
    "hide_power",
    "hide_cadence",
    "hide_elevation",
    "hide_speed",
    "hide_pace",
    "hide_laps",
    "hide_workout_sets_steps",
    "hide_gear",
)

START = datetime(2026, 7, 27, tzinfo=UTC)
END = datetime(2026, 8, 2, tzinfo=UTC)


@pytest.fixture
def db():
    session = create_sqlite_session()
    # The local-date filter calls PostgreSQL's ``timezone()``. These activities are all UTC, so the
    # stand-in returns the stored instant unchanged; ``tests/postgres`` runs the real function.
    session.connection().connection.driver_connection.create_function("timezone", 2, lambda _tz, value: value)
    yield session
    session.close()
    session.bind.dispose()


def _add(db, **overrides):
    data = {
        "user_id": 1,
        "name": "Activity",
        "distance": 1000,
        "activity_type": 1,
        "start_time": "2026-07-28T09:00:00",
        "end_time": "2026-07-28T10:00:00",
        "timezone": "UTC",
        "total_elapsed_time": 700.0,
        "total_timer_time": 600.0,
        "calories": 100,
        "visibility": 0,
        **{flag: False for flag in _PRIVACY_FLAGS},
    }
    data.update(overrides)
    activity_crud.create_activity(activity_contracts.ActivityCore(**data), db)


def _sum(db, **overrides):
    kwargs = {"user_is_owner": True, **overrides}
    totals = activity_crud.sum_user_activities_per_timeframe_by_type(1, START, END, db, **kwargs)
    return {total.activity_type: total for total in totals}


class TestSumPerType:
    def test_adds_up_distance_active_time_and_calories_per_activity_type(self, db):
        _add(db, activity_type=1, distance=1000, total_timer_time=600.0, calories=100)
        _add(db, activity_type=1, distance=2500, total_timer_time=900.0, calories=150, start_time="2026-07-29T09:00:00")
        _add(db, activity_type=4, distance=30000, total_timer_time=5400.0, calories=800)

        totals = _sum(db)

        assert set(totals) == {1, 4}
        assert (totals[1].distance, totals[1].time, totals[1].calories) == (3500.0, 1500.0, 250.0)
        assert (totals[4].distance, totals[4].time, totals[4].calories) == (30000.0, 5400.0, 800.0)

    def test_an_activity_without_calories_counts_as_zero(self, db):
        _add(db, calories=None)
        _add(db, calories=40, start_time="2026-07-29T09:00:00")

        assert _sum(db)[1].calories == 40.0

    def test_only_the_users_own_activities_in_the_window_count(self, db):
        _add(db)
        _add(db, user_id=2)
        _add(db, start_time="2026-06-01T09:00:00", end_time="2026-06-01T10:00:00")
        _add(db, start_time="2026-08-03T09:00:00", end_time="2026-08-03T10:00:00")

        assert _sum(db)[1].distance == 1000.0

    def test_the_window_includes_its_last_day(self, db):
        _add(db, start_time="2026-08-02T09:00:00", end_time="2026-08-02T10:00:00")

        assert _sum(db)[1].distance == 1000.0

    def test_no_activities_give_no_rows(self, db):
        assert activity_crud.sum_user_activities_per_timeframe_by_type(1, START, END, db, user_is_owner=True) == []


class TestVisibility:
    @pytest.fixture(autouse=True)
    def _activities(self, db):
        # Distinct start times: activities that share one are flagged as duplicates and hidden.
        _add(db, visibility=0, distance=1000, start_time="2026-07-28T09:00:00")  # public
        _add(db, visibility=1, distance=2000, start_time="2026-07-29T09:00:00")  # followers
        _add(db, visibility=2, distance=4000, start_time="2026-07-30T09:00:00")  # private

    def test_the_owner_counts_everything(self, db):
        assert _sum(db)[1].distance == 7000.0

    def test_a_stranger_counts_only_public_activities(self, db):
        assert _sum(db, user_is_owner=False, followee_ids=[])[1].distance == 1000.0

    def test_a_follower_also_counts_followers_only_activities(self, db):
        assert _sum(db, user_is_owner=False, followee_ids=[1])[1].distance == 3000.0

    def test_an_anonymous_reader_counts_only_public_activities(self, db):
        assert _sum(db, user_is_owner=False, followee_ids=None)[1].distance == 1000.0
