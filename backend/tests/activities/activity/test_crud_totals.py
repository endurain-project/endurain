"""The sums the database adds up for stats, goals and gear usage, on PostgreSQL."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.crud as activity_crud
import modules.gears.contracts as gears_contracts
from tests._factories.activities import make_activity, make_activity_at
from tests._factories.gears import make_gear
from tests._factories.users import make_user

_Visibility = activity_constants.ActivityVisibility
_Type = activity_constants.ActivityType
_WINDOW = (datetime(2026, 7, 27, tzinfo=UTC), datetime(2026, 8, 2, tzinfo=UTC))
_DAY = datetime(2026, 7, 28, 9, tzinfo=UTC)


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def other(db):
    return make_user(db, timezone="UTC")


def _by_type(db, user_id, **kwargs):
    totals = activity_crud.sum_user_activities_per_timeframe_by_type(user_id, *_WINDOW, db, **kwargs)
    return {total.activity_type: total for total in totals}


class TestSumPerType:
    def test_distance_active_time_and_calories_are_added_up_per_activity_type(self, db, owner):
        make_activity_at(db, owner.id, _DAY, activity_type=1, distance=1000, total_timer_time=600.0, calories=100)
        make_activity_at(
            db,
            owner.id,
            _DAY + timedelta(days=1),
            activity_type=1,
            distance=2500,
            total_timer_time=600.0,
            calories=None,
        )
        make_activity_at(
            db, owner.id, _DAY + timedelta(days=2), activity_type=4, distance=30000, total_timer_time=5400.0
        )

        totals = _by_type(db, owner.id, user_is_owner=True)

        assert (totals[1].distance, totals[1].time, totals[1].calories) == (3500.0, 1200.0, 100.0)
        assert (totals[4].distance, totals[4].time) == (30000.0, 5400.0)

    def test_the_window_is_the_activitys_own_local_calendar_days_and_includes_its_last_day(self, db, owner):
        # 23:30 UTC on 2 August is already 3 August in Auckland (outside); 23:30 UTC on 26 July is 27 July there.
        make_activity_at(db, owner.id, datetime(2026, 8, 2, 23, 30, tzinfo=UTC), timezone="Pacific/Auckland")
        make_activity_at(
            db, owner.id, datetime(2026, 7, 26, 23, 30, tzinfo=UTC), timezone="Pacific/Auckland", distance=7000
        )
        make_activity_at(db, owner.id, datetime(2026, 8, 2, 22, 0, tzinfo=UTC), timezone="UTC", distance=11)

        assert _by_type(db, owner.id, user_is_owner=True)[1].distance == 7011.0

    def test_only_the_users_own_activities_count(self, db, owner, other):
        make_activity(db, other.id, start_time=_DAY, end_time=_DAY + timedelta(hours=1))

        assert _by_type(db, owner.id, user_is_owner=True) == {}

    def test_a_reader_counts_what_the_visibility_lets_them_see(self, db, owner):
        make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC, distance=1000)
        make_activity_at(db, owner.id, _DAY + timedelta(days=1), visibility=_Visibility.FOLLOWERS, distance=2000)
        make_activity_at(db, owner.id, _DAY + timedelta(days=2), visibility=_Visibility.PRIVATE, distance=4000)

        assert _by_type(db, owner.id, user_is_owner=True)[1].distance == 7000.0
        assert _by_type(db, owner.id, user_is_owner=False, followee_ids=[])[1].distance == 1000.0
        assert _by_type(db, owner.id, user_is_owner=False, followee_ids=[owner.id])[1].distance == 3000.0
        assert _by_type(db, owner.id, user_is_owner=False)[1].distance == 1000.0

    def test_a_reader_does_not_count_an_activity_whose_start_is_hidden(self, db, owner):
        make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC, hide_start_time=True)

        assert _by_type(db, owner.id, user_is_owner=False) == {}
        assert _by_type(db, owner.id, user_is_owner=True)[1].distance == 10000.0


class TestSumByTypesForGoals:
    _GOAL_WINDOW = (datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 31, tzinfo=UTC))

    def _totals(self, db, user_id, types=(1,), **kwargs):
        return activity_crud.sum_user_activities_per_timeframe_and_activity_types(
            user_id, list(types), *self._GOAL_WINDOW, db, **kwargs
        )

    def test_nothing_matching_is_all_zero(self, db, owner):
        make_activity_at(db, owner.id, datetime(2026, 7, 10, tzinfo=UTC))

        totals = self._totals(db, owner.id, types=(2,))

        assert (totals.count, totals.calories, totals.distance, totals.elevation_gain, totals.elapsed_time) == (
            0,
            0,
            0,
            0,
            0,
        )

    def test_activities_are_summed_and_missing_values_count_as_zero(self, db, owner):
        make_activity_at(db, owner.id, datetime(2026, 7, 10, tzinfo=UTC))
        make_activity_at(db, owner.id, datetime(2026, 7, 11, tzinfo=UTC), elevation_gain=50, calories=200)

        totals = self._totals(db, owner.id)

        assert (totals.count, totals.distance, totals.elapsed_time) == (2, 20000, 7200)
        assert (totals.calories, totals.elevation_gain) == (200, 50)

    def test_a_hidden_activity_is_left_out_only_when_asked(self, db, owner):
        make_activity_at(db, owner.id, datetime(2026, 7, 10, tzinfo=UTC))
        make_activity_at(db, owner.id, datetime(2026, 7, 11, tzinfo=UTC), is_hidden=True)

        assert self._totals(db, owner.id).count == 2
        assert self._totals(db, owner.id, exclude_hidden=True).count == 1

    def test_other_users_and_other_types_are_not_counted(self, db, owner, other):
        make_activity_at(db, other.id, datetime(2026, 7, 10, tzinfo=UTC))
        make_activity_at(db, owner.id, datetime(2026, 7, 10, tzinfo=UTC), activity_type=_Type.RIDE.stored)

        assert self._totals(db, owner.id).count == 0

    def test_the_activities_of_a_window_come_newest_first_and_follow_the_visibility(self, db, owner):
        old = make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC)
        new = make_activity_at(db, owner.id, _DAY + timedelta(days=1), visibility=_Visibility.PUBLIC)
        private = make_activity_at(db, owner.id, _DAY + timedelta(days=2), visibility=_Visibility.PRIVATE)
        make_activity_at(db, owner.id, _DAY + timedelta(days=3), visibility=_Visibility.PUBLIC, is_hidden=True)

        as_owner = activity_crud.get_user_activities_per_timeframe_and_activity_types(
            owner.id, [1], *_WINDOW, db, user_is_owner=True, exclude_hidden=True
        )
        as_reader = activity_crud.get_user_activities_per_timeframe_and_activity_types(
            owner.id, [1], *_WINDOW, db, user_is_owner=False
        )
        nothing = activity_crud.get_user_activities_per_timeframe_and_activity_types(
            owner.id, [4], *_WINDOW, db, user_is_owner=True
        )

        assert [a.id for a in as_owner] == [private.id, new.id, old.id]
        assert [a.id for a in as_reader] == [new.id, old.id]
        assert nothing == []


class TestGearUsage:
    def test_the_distance_and_moving_time_of_the_owners_activities_on_the_gear_are_added_up(self, db, owner, other):
        gear = make_gear(db, owner.id)
        make_activity_at(db, owner.id, _DAY, gear_id=gear.id, distance=1000, total_timer_time=100.0)
        make_activity_at(db, owner.id, _DAY + timedelta(days=1), gear_id=gear.id, distance=2000, total_timer_time=50.0)
        make_activity_at(db, owner.id, _DAY + timedelta(days=2), distance=9999)
        make_activity_at(db, other.id, _DAY, gear_id=gear.id, distance=5000)

        usage = activity_crud.sum_gear_usage(gear.id, owner.id, db)

        assert (usage.distance, usage.time) == (3000.0, 150.0)

    def test_a_gear_without_activities_has_zero_usage(self, db, owner):
        gear = make_gear(db, owner.id)

        usage = activity_crud.sum_gear_usage(gear.id, owner.id, db)

        assert (usage.distance, usage.time) == (0.0, 0.0)

    def test_each_window_adds_up_the_activities_on_its_local_days_and_every_key_is_answered(self, db, owner):
        gear = make_gear(db, owner.id)
        make_activity_at(db, owner.id, datetime(2026, 7, 1, 10, tzinfo=UTC), gear_id=gear.id, distance=1000)
        make_activity_at(db, owner.id, datetime(2026, 7, 15, 10, tzinfo=UTC), gear_id=gear.id, distance=2000)
        make_activity_at(
            db,
            owner.id,
            datetime(2026, 7, 31, 23, 30, tzinfo=UTC),
            gear_id=gear.id,
            distance=4000,
            timezone="Pacific/Auckland",
        )
        windows = [
            gears_contracts.UsageWindow(key=gear.id, start_date=date(2026, 7, 10), end_date=date(2026, 7, 20)),
            gears_contracts.UsageWindow(key=owner.id, start_date=date(2026, 8, 1), end_date=None),
            gears_contracts.UsageWindow(key=uuid.uuid4(), start_date=date(2030, 1, 1), end_date=None),
        ]

        usage = activity_crud.sum_gear_usage_by_window(gear.id, owner.id, windows, db)

        assert usage[gear.id].distance == 2000.0
        assert usage[owner.id].distance == 4000.0
        assert usage[windows[2].key].distance == 0.0

    def test_no_windows_give_no_totals(self, db, owner):
        assert activity_crud.sum_gear_usage_by_window(make_gear(db, owner.id).id, owner.id, [], db) == {}
