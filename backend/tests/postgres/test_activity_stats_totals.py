"""The per-type stats sums run against real PostgreSQL, including its ``timezone()`` date filter."""

from datetime import UTC, datetime

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
from tests._helpers.db import ensure_user

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

_WINDOW = (datetime(2026, 7, 27, tzinfo=UTC), datetime(2026, 8, 2, tzinfo=UTC))


def _add(factory, **overrides):
    ensure_user(factory, overrides.get("user_id", 1))
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
    with factory() as db:
        activity_crud.create_activity(activity_contracts.ActivityCore(**data), db)
        db.commit()


def _sum(factory, **kwargs):
    with factory() as db:
        totals = activity_crud.sum_user_activities_per_timeframe_by_type(1, *_WINDOW, db, **kwargs)
    return {total.activity_type: total for total in totals}


def test_sums_are_grouped_per_activity_type(pg_factory):
    _add(pg_factory, activity_type=1, distance=1000, calories=100)
    _add(pg_factory, activity_type=1, distance=2500, calories=None, start_time="2026-07-29T09:00:00")
    _add(pg_factory, activity_type=4, distance=30000, total_timer_time=5400.0, start_time="2026-07-30T09:00:00")

    totals = _sum(pg_factory, user_is_owner=True)

    assert (totals[1].distance, totals[1].time, totals[1].calories) == (3500.0, 1200.0, 100.0)
    assert (totals[4].distance, totals[4].time) == (30000.0, 5400.0)


def test_the_window_is_the_activitys_own_local_calendar_days(pg_factory):
    # 23:30 UTC on Aug 2 is already Aug 3 in Auckland (outside the window), while
    # 23:30 UTC on Jul 26 is Jul 27 in Auckland (inside it).
    _add(pg_factory, timezone="Pacific/Auckland", start_time="2026-08-02T23:30:00", end_time="2026-08-03T00:30:00")
    _add(
        pg_factory,
        timezone="Pacific/Auckland",
        distance=7000,
        start_time="2026-07-26T23:30:00",
        end_time="2026-07-27T00:30:00",
    )

    assert _sum(pg_factory, user_is_owner=True)[1].distance == 7000.0


def test_a_stranger_counts_only_public_activities(pg_factory):
    _add(pg_factory, visibility=0, distance=1000, start_time="2026-07-28T09:00:00")
    _add(pg_factory, visibility=1, distance=2000, start_time="2026-07-29T09:00:00")
    _add(pg_factory, visibility=2, distance=4000, start_time="2026-07-30T09:00:00")

    assert _sum(pg_factory, user_is_owner=True)[1].distance == 7000.0
    assert _sum(pg_factory, user_is_owner=False, followee_ids=[])[1].distance == 1000.0
    assert _sum(pg_factory, user_is_owner=False, followee_ids=[1])[1].distance == 3000.0


def test_no_activities_give_no_rows(pg_factory):
    ensure_user(pg_factory, 1)

    assert _sum(pg_factory, user_is_owner=True) == {}
