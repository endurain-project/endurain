"""The activity summaries bucket by the activity's own local day, week, month and year, against real PostgreSQL.

The buckets come from ``timezone(zone, start_time)`` (``AT TIME ZONE``), which the unit tests only compile or run on
SQLite stand-ins. These runs put activities near midnight in zones far from UTC and either side of a daylight-saving
change, where a fixed offset, or a UTC bucket, puts them in the wrong period.
"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session
from tests._factories.users import make_user

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.summary_crud as summary_crud

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


def _add(
    db: Session,
    user_id: uuid.UUID,
    start_utc: str,
    timezone: str | None,
    *,
    distance: int = 1000,
    activity_type: int = 1,
) -> None:
    """Stage an activity starting at a UTC instant (``2026-07-26T12:30:00Z``) in an IANA zone."""
    start = datetime.fromisoformat(start_utc)
    activity_crud.create_activity(
        activity_contracts.ActivityCore(
            user_id=user_id,
            name=f"Activity {start_utc}",
            distance=distance,
            activity_type=activity_type,
            start_time=start_utc,
            end_time=(start + timedelta(minutes=20)).isoformat(),
            timezone=timezone,
            total_elapsed_time=1300.0,
            total_timer_time=1200.0,
            calories=100,
            visibility=0,
            **{flag: False for flag in _PRIVACY_FLAGS},
        ),
        db,
    )


@pytest.fixture
def user_id(db) -> uuid.UUID:
    return make_user(db).id


def _days(summary) -> dict[int, int]:
    """Activity count per day index (0 = Monday) of a weekly summary, days without activities left out."""
    return {day.day_of_week: day.activity_count for day in summary.breakdown if day.activity_count}


class TestWeeklySummary:
    def test_an_activity_just_after_local_midnight_is_on_the_local_day_not_the_utc_one(self, db, user_id):
        # 12:30 UTC on Sunday 26 Jul is 00:30 on Monday 27 Jul in Auckland (UTC+12).
        _add(db, user_id, "2026-07-26T12:30:00Z", "Pacific/Auckland")

        this_week = summary_crud.get_weekly_summary(user_id, date(2026, 7, 29), "monday", db)
        previous_week = summary_crud.get_weekly_summary(user_id, date(2026, 7, 22), "monday", db)

        assert _days(this_week) == {0: 1}
        assert previous_week.activity_count == 0

    def test_an_activity_just_before_local_midnight_stays_on_the_earlier_local_day(self, db, user_id):
        # 03:30 UTC on Monday 27 Jul is 20:30 on Sunday 26 Jul in Los Angeles (UTC-7).
        _add(db, user_id, "2026-07-27T03:30:00Z", "America/Los_Angeles")

        previous_week = summary_crud.get_weekly_summary(user_id, date(2026, 7, 22), "monday", db)
        this_week = summary_crud.get_weekly_summary(user_id, date(2026, 7, 29), "monday", db)

        assert _days(previous_week) == {6: 1}
        assert this_week.activity_count == 0

    def test_a_week_starting_on_sunday_puts_the_same_activity_in_the_week_it_opens(self, db, user_id):
        _add(db, user_id, "2026-07-26T12:30:00Z", "Pacific/Auckland")

        summary = summary_crud.get_weekly_summary(user_id, date(2026, 7, 29), "sunday", db)

        assert _days(summary) == {0: 1}

    def test_an_activity_without_a_zone_is_bucketed_in_utc(self, db, user_id):
        _add(db, user_id, "2026-07-26T23:30:00Z", None)

        summary = summary_crud.get_weekly_summary(user_id, date(2026, 7, 22), "monday", db)

        assert _days(summary) == {6: 1}

    def test_days_either_side_of_the_end_of_daylight_saving_keep_their_local_day(self, db, user_id):
        # Auckland leaves daylight saving at 03:00 on Sunday 5 Apr 2026 (UTC+13 becomes UTC+12 at 14:00 UTC on the 4th).
        _add(db, user_id, "2026-04-04T11:30:00Z", "Pacific/Auckland")  # 00:30 NZDT, Sunday 5 Apr
        _add(db, user_id, "2026-04-05T11:30:00Z", "Pacific/Auckland")  # 23:30 NZST, Sunday 5 Apr
        _add(db, user_id, "2026-04-05T12:30:00Z", "Pacific/Auckland")  # 00:30 NZST, Monday 6 Apr

        week_of_the_change = summary_crud.get_weekly_summary(user_id, date(2026, 4, 1), "monday", db)
        next_week = summary_crud.get_weekly_summary(user_id, date(2026, 4, 8), "monday", db)

        assert _days(week_of_the_change) == {6: 2}
        assert _days(next_week) == {0: 1}

    def test_days_either_side_of_the_start_of_daylight_saving_keep_their_local_day(self, db, user_id):
        # New York springs forward at 02:00 on Sunday 8 Mar 2026 (07:00 UTC).
        _add(db, user_id, "2026-03-08T06:30:00Z", "America/New_York")  # 01:30 EST, Sunday 8 Mar
        _add(db, user_id, "2026-03-08T07:30:00Z", "America/New_York")  # 03:30 EDT, Sunday 8 Mar
        _add(db, user_id, "2026-03-09T03:30:00Z", "America/New_York")  # 23:30 EDT, Sunday 8 Mar
        _add(db, user_id, "2026-03-09T04:30:00Z", "America/New_York")  # 00:30 EDT, Monday 9 Mar

        week = summary_crud.get_weekly_summary(user_id, date(2026, 3, 4), "monday", db)
        next_week = summary_crud.get_weekly_summary(user_id, date(2026, 3, 11), "monday", db)

        assert _days(week) == {6: 3}
        assert _days(next_week) == {0: 1}

    def test_another_users_activities_and_other_types_are_left_out(self, db, user_id):
        other_user_id = make_user(db).id
        _add(db, user_id, "2026-07-28T09:30:00Z", "UTC", distance=1000, activity_type=1)
        _add(db, user_id, "2026-07-29T09:30:00Z", "UTC", distance=5000, activity_type=4)
        _add(db, other_user_id, "2026-07-28T10:30:00Z", "UTC", distance=9000)

        everything = summary_crud.get_weekly_summary(user_id, date(2026, 7, 29), "monday", db)
        rides = summary_crud.get_weekly_summary(
            user_id, date(2026, 7, 29), "monday", db, activity_type=activity_constants.ActivityType.RIDE
        )

        assert everything.total_distance == 6000.0
        assert (rides.total_distance, rides.activity_count) == (5000.0, 1)


class TestMonthlySummary:
    def test_the_month_and_its_week_follow_the_local_date(self, db, user_id):
        # 03:30 UTC on 1 Aug is 20:30 on 31 Jul in Los Angeles; 12:30 UTC on 26 Jul is 27 Jul in Auckland.
        _add(db, user_id, "2026-08-01T03:30:00Z", "America/Los_Angeles")
        _add(db, user_id, "2026-07-26T12:30:00Z", "Pacific/Auckland")

        july = summary_crud.get_monthly_summary(user_id, date(2026, 7, 15), "monday", db)
        august = summary_crud.get_monthly_summary(user_id, date(2026, 8, 15), "monday", db)

        # 1 Jul 2026 is a Wednesday, so 27 Jul opens the fifth week and 31 Jul closes it.
        assert {week.week_number: week.activity_count for week in july.breakdown} == {5: 2}
        assert august.activity_count == 0


class TestYearlySummary:
    def test_the_year_and_month_follow_the_local_date_across_new_year(self, db, user_id):
        # 23:30 UTC on 31 Dec is 12:30 on 1 Jan in Auckland; 03:00 UTC on 1 Jan is 19:00 on 31 Dec in Los Angeles.
        _add(db, user_id, "2026-12-31T23:30:00Z", "Pacific/Auckland")
        _add(db, user_id, "2027-01-01T03:30:00Z", "America/Los_Angeles")

        year_2026 = summary_crud.get_yearly_summary(user_id, 2026, db)
        year_2027 = summary_crud.get_yearly_summary(user_id, 2027, db)

        assert {month.month_number: month.activity_count for month in year_2026.breakdown if month.activity_count} == {
            12: 1
        }
        assert {month.month_number: month.activity_count for month in year_2027.breakdown if month.activity_count} == {
            1: 1
        }


class TestLifetimeSummary:
    def test_each_activity_counts_in_its_local_year(self, db, user_id):
        _add(db, user_id, "2026-12-31T23:30:00Z", "Pacific/Auckland")
        _add(db, user_id, "2027-01-01T03:30:00Z", "America/Los_Angeles")

        summary = summary_crud.get_lifetime_summary(user_id, db)

        assert summary.activity_count == 2
        assert {year.year_number: year.activity_count for year in summary.breakdown} == {2027: 1, 2026: 1}
        assert [item.activity_count for item in summary.type_breakdown] == [2]

    def test_a_user_without_activities_has_an_empty_summary(self, db, user_id):
        summary = summary_crud.get_lifetime_summary(user_id, db)

        assert (summary.activity_count, summary.breakdown, summary.type_breakdown) == (0, [], [])
