"""The aggregated chart queries against real PostgreSQL.

The unit tests compile the statements; this runs them, so ``date_trunc``, the ``AT TIME ZONE`` day of a
bowel movement and the average over a nullable column are checked by the database that serves them.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

import core.date_range as core_date_range
import modules.health.constants as health_constants
import modules.health.health_poop.crud as poop_crud
import modules.health.health_poop.models as poop_models
import modules.health.health_sleep.crud as sleep_crud
import modules.health.health_sleep.models as sleep_models
import modules.health.health_steps.crud as steps_crud
import modules.health.health_steps.models as steps_models
import modules.health.health_water.crud as water_crud
import modules.health.health_water.models as water_models
import modules.health.health_weight.crud as weight_crud
import modules.health.health_weight.models as weight_models
from tests._helpers.db import ensure_user

_BUCKET = health_constants.ChartBucket
_SINCE = date(2026, 1, 1)


@pytest.fixture
def db(pg_factory):
    for user_id in (1, 2):
        ensure_user(pg_factory, user_id)
    with pg_factory() as session:
        yield session


def _points(points):
    return [(point.date, point.value) for point in points]


def test_steps_average_per_day_week_and_month(db):
    # 2026-03-02 and 2026-03-04 share a week (Monday 2026-03-02); 2026-03-09 starts the next one.
    db.add_all(
        steps_models.HealthSteps(user_id=1, date=day, steps=steps)
        for day, steps in ((date(2026, 3, 2), 4000), (date(2026, 3, 4), 8000), (date(2026, 3, 9), 6000))
    )
    db.add(steps_models.HealthSteps(user_id=2, date=date(2026, 3, 2), steps=99999))
    db.commit()

    assert _points(steps_crud.get_health_steps_chart(1, _SINCE, None, _BUCKET.DAY, db)) == [
        (date(2026, 3, 2), 4000.0),
        (date(2026, 3, 4), 8000.0),
        (date(2026, 3, 9), 6000.0),
    ]
    assert _points(steps_crud.get_health_steps_chart(1, _SINCE, None, _BUCKET.WEEK, db)) == [
        (date(2026, 3, 2), 6000.0),
        (date(2026, 3, 9), 6000.0),
    ]
    assert _points(steps_crud.get_health_steps_chart(1, _SINCE, None, _BUCKET.MONTH, db)) == [
        (date(2026, 3, 1), 6000.0)
    ]


def test_the_window_excludes_earlier_days(db):
    db.add_all(
        steps_models.HealthSteps(user_id=1, date=day, steps=1000) for day in (date(2025, 12, 31), date(2026, 1, 1))
    )
    db.commit()

    assert _points(steps_crud.get_health_steps_chart(1, _SINCE, None, _BUCKET.DAY, db)) == [(date(2026, 1, 1), 1000.0)]
    assert len(steps_crud.get_health_steps_chart(1, date.min, None, _BUCKET.DAY, db)) == 2


def test_the_bucket_the_window_opens_in_is_dated_the_window_start(db):
    # 2026-03-04 is a Wednesday: its week starts on Monday 03-02, before the window does.
    db.add_all(
        steps_models.HealthSteps(user_id=1, date=day, steps=steps)
        for day, steps in ((date(2026, 3, 3), 1000), (date(2026, 3, 4), 3000), (date(2026, 3, 9), 5000))
    )
    db.commit()

    assert _points(steps_crud.get_health_steps_chart(1, date(2026, 3, 4), None, _BUCKET.WEEK, db)) == [
        (date(2026, 3, 4), 3000.0),
        (date(2026, 3, 9), 5000.0),
    ]
    assert _points(steps_crud.get_health_steps_chart(1, date(2026, 3, 4), None, _BUCKET.MONTH, db)) == [
        (date(2026, 3, 4), 4000.0)
    ]


def test_weight_and_water_average_their_decimals(db):
    db.add_all(
        weight_models.HealthWeight(user_id=1, date=date(2026, 3, day), weight=Decimal(kg))
        for day, kg in ((2, "70.0"), (3, "71.0"))
    )
    db.add_all(
        water_models.HealthWater(user_id=1, date=date(2026, 3, day), amount_ml=Decimal(ml))
        for day, ml in ((2, "1500"), (3, "2500"))
    )
    db.commit()

    assert _points(weight_crud.get_health_weight_chart(1, _SINCE, None, _BUCKET.WEEK, db)) == [(date(2026, 3, 2), 70.5)]
    assert _points(water_crud.get_health_water_chart(1, _SINCE, None, _BUCKET.WEEK, db)) == [(date(2026, 3, 2), 2000.0)]


def test_sleep_and_resting_heart_rate_skip_days_without_a_value(db):
    db.add_all(
        [
            sleep_models.HealthSleep(
                user_id=1, date=date(2026, 3, 2), total_sleep_seconds=28800, resting_heart_rate=50
            ),
            sleep_models.HealthSleep(user_id=1, date=date(2026, 3, 3), total_sleep_seconds=None, resting_heart_rate=54),
            sleep_models.HealthSleep(
                user_id=1, date=date(2026, 3, 4), total_sleep_seconds=21600, resting_heart_rate=None
            ),
        ]
    )
    db.commit()

    assert _points(sleep_crud.get_health_sleep_chart(1, _SINCE, None, _BUCKET.WEEK, db)) == [
        (date(2026, 3, 2), 25200.0)
    ]
    assert _points(sleep_crud.get_health_sleep_resting_heart_rate_chart(1, _SINCE, None, _BUCKET.WEEK, db)) == [
        (date(2026, 3, 2), 52.0)
    ]


def test_poop_counts_per_day_of_the_users_timezone(db):
    # 23:30 UTC on 2026-03-02 is already 2026-03-03 in Tokyo.
    db.add_all(
        poop_models.HealthPoop(user_id=1, date_time=moment)
        for moment in (
            datetime(2026, 3, 2, 23, 30, tzinfo=UTC),
            datetime(2026, 3, 3, 1, 0, tzinfo=UTC),
            datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
        )
    )
    db.commit()

    assert _points(poop_crud.get_health_poop_chart(1, _SINCE, None, _BUCKET.DAY, "UTC", db)) == [
        (date(2026, 3, 2), 1.0),
        (date(2026, 3, 3), 1.0),
        (date(2026, 3, 9), 1.0),
    ]
    assert _points(poop_crud.get_health_poop_chart(1, _SINCE, None, _BUCKET.DAY, "Asia/Tokyo", db)) == [
        (date(2026, 3, 3), 2.0),
        (date(2026, 3, 9), 1.0),
    ]
    assert _points(poop_crud.get_health_poop_chart(1, _SINCE, None, _BUCKET.MONTH, "UTC", db)) == [
        (date(2026, 3, 1), 3.0)
    ]


def test_poop_first_day_is_in_the_users_timezone(db):
    assert poop_crud.get_health_poop_first_day(1, "UTC", db) is None

    db.add_all(
        poop_models.HealthPoop(user_id=1, date_time=moment)
        for moment in (datetime(2026, 3, 2, 23, 30, tzinfo=UTC), datetime(2026, 3, 9, 12, 0, tzinfo=UTC))
    )
    db.add(poop_models.HealthPoop(user_id=2, date_time=datetime(2025, 1, 1, 12, 0, tzinfo=UTC)))
    db.commit()

    assert poop_crud.get_health_poop_first_day(1, "UTC", db) == date(2026, 3, 2)
    assert poop_crud.get_health_poop_first_day(1, "Asia/Tokyo", db) == date(2026, 3, 3)


def test_poop_list_and_count_filter_on_the_users_local_day(db):
    # 23:30 UTC on 2026-03-02 is already 2026-03-03 in Tokyo, so a window opening on 03-03 includes it there.
    db.add(poop_models.HealthPoop(user_id=1, date_time=datetime(2026, 3, 2, 23, 30, tzinfo=UTC)))
    db.commit()
    since = date(2026, 3, 3)

    assert poop_crud.get_health_poop_number_by_user_id(1, db, since, None, "Asia/Tokyo") == 1
    assert len(poop_crud.get_health_poop_by_user_id(1, db, 1, 10, since, None, "Asia/Tokyo")) == 1
    assert poop_crud.get_health_poop_number_by_user_id(1, db, since, None, "UTC") == 0
    assert poop_crud.get_health_poop_by_user_id(1, db, 1, 10, since, None, "UTC") == []


def test_every_interval_charts_its_whole_range(db):
    """~500 daily records: each interval covers its whole range, daily until a year of bars is exceeded."""
    import modules.health.health_steps.service as steps_service

    today = date(2026, 10, 28)
    db.add_all(
        steps_models.HealthSteps(user_id=1, date=today - timedelta(days=offset), steps=1000 + offset)
        for offset in range(500)
    )
    db.commit()

    with patch("modules.users.users.integration_service.local_today", return_value=today):
        sizes = {
            interval: steps_service.get_health_steps_chart(1, interval, db) for interval in health_constants.Interval
        }

    assert {interval: (series.bucket, len(series.points)) for interval, series in sizes.items()} == {
        health_constants.Interval.LAST_7_DAYS: (_BUCKET.DAY, 8),
        health_constants.Interval.LAST_30_DAYS: (_BUCKET.DAY, 31),
        health_constants.Interval.LAST_90_DAYS: (_BUCKET.DAY, 91),
        health_constants.Interval.LAST_YEAR: (_BUCKET.DAY, 366),
        # 500 daily records exceed a year of bars, so the whole history is charted weekly.
        health_constants.Interval.ALL_TIME: (_BUCKET.WEEK, len(sizes[health_constants.Interval.ALL_TIME].points)),
    }
    assert 71 <= len(sizes[health_constants.Interval.ALL_TIME].points) <= 73


def test_poop_all_time_chart_reaches_the_earliest_allowed_time_in_a_negative_offset_zone(db):
    """1900-01-01 00:30 UTC is 1899-12-31 in Los Angeles; the chart still finds it and buckets it."""
    import modules.health.health_poop.service as poop_service

    db.add_all(
        poop_models.HealthPoop(user_id=1, date_time=moment)
        for moment in (datetime(1900, 1, 1, 0, 30, tzinfo=UTC), datetime(2026, 3, 9, 12, 0, tzinfo=UTC))
    )
    db.commit()

    with (
        patch("modules.users.users.integration_service.local_today", return_value=date(2026, 3, 10)),
        patch("modules.users.users.integration_service.resolve_timezone", return_value="America/Los_Angeles"),
    ):
        series = poop_service.get_health_poop_chart(1, health_constants.Interval.ALL_TIME, db)

    assert series.points[0].date == date(1899, 12, 31)
    assert len(series.points) == 2


def _steps(db, days):
    db.add_all(
        steps_models.HealthSteps(user_id=1, date=day, steps=1000 * (index + 1)) for index, day in enumerate(days)
    )
    db.commit()


def test_steps_past_window_with_both_dates(db):
    import modules.health.health_steps.service as steps_service

    _steps(db, [date(2026, 1, 5), date(2026, 2, 10), date(2026, 2, 11), date(2026, 3, 20)])
    window = core_date_range.DateRange(date(2026, 2, 10), date(2026, 2, 11))

    with patch("modules.users.users.integration_service.local_today", return_value=date(2026, 10, 28)):
        series = steps_service.get_health_steps_chart(1, health_constants.Interval.LAST_7_DAYS, db, date_range=window)
        page = steps_service.list_health_steps(1, db, date_range=window)

    assert _points(series.points) == [(date(2026, 2, 10), 2000.0), (date(2026, 2, 11), 3000.0)]
    assert (page.total, sorted(item.steps for item in page.items)) == (2, [2000, 3000])


def test_steps_open_ended_ranges(db):
    import modules.health.health_steps.service as steps_service

    _steps(db, [date(2026, 1, 5), date(2026, 2, 10), date(2026, 3, 20)])

    with patch("modules.users.users.integration_service.local_today", return_value=date(2026, 10, 28)):
        from_start = steps_service.list_health_steps(1, db, date_range=core_date_range.DateRange(date(2026, 2, 10)))
        until_end = steps_service.list_health_steps(
            1, db, date_range=core_date_range.DateRange(None, date(2026, 2, 10))
        )
        chart_until = steps_service.get_health_steps_chart(
            1,
            health_constants.Interval.LAST_7_DAYS,
            db,
            date_range=core_date_range.DateRange(None, date(2026, 2, 10)),
        )
        unchanged = steps_service.list_health_steps(1, db)

    assert sorted(item.steps for item in from_start.items) == [2000, 3000]
    assert sorted(item.steps for item in until_end.items) == [1000, 2000]
    assert _points(chart_until.points) == [(date(2026, 1, 5), 1000.0), (date(2026, 2, 10), 2000.0)]
    assert unchanged.total == 3


def test_poop_window_is_the_users_local_days(db):
    import modules.health.health_poop.service as poop_service

    # 23:30 UTC on 03-02 is 03-03 in Tokyo; 15:30 UTC on 03-03 is 03-04 in Tokyo.
    db.add_all(
        poop_models.HealthPoop(user_id=1, date_time=moment)
        for moment in (
            datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            datetime(2026, 3, 2, 23, 30, tzinfo=UTC),
            datetime(2026, 3, 3, 15, 30, tzinfo=UTC),
            datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
        )
    )
    db.commit()
    both = core_date_range.DateRange(date(2026, 3, 3), date(2026, 3, 3))
    only_end = core_date_range.DateRange(None, date(2026, 3, 3))
    only_start = core_date_range.DateRange(date(2026, 3, 4))

    with (
        patch("modules.users.users.integration_service.local_today", return_value=date(2026, 10, 28)),
        patch("modules.users.users.integration_service.resolve_timezone", return_value="Asia/Tokyo"),
    ):
        one_day = poop_service.list_health_poop(1, db, date_range=both)
        until = poop_service.list_health_poop(1, db, date_range=only_end)
        after = poop_service.list_health_poop(1, db, date_range=only_start)
        chart = poop_service.get_health_poop_chart(1, health_constants.Interval.LAST_7_DAYS, db, date_range=only_end)
        everything = poop_service.list_health_poop(1, db)

    # Tokyo days: 03-01 21:00 -> 03-01, 03-03 08:30 -> 03-03, 03-04 00:30 -> 03-04, 03-09 21:00 -> 03-09.
    assert one_day.total == 1
    assert until.total == 2
    assert after.total == 2
    assert everything.total == 4
    # The chart opens at the first movement and closes on the end date.
    assert _points(chart.points) == [(date(2026, 3, 1), 1.0), (date(2026, 3, 3), 1.0)]
