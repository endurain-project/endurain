"""The aggregated chart series every health metric serves beside its paginated list, on the real database."""

from datetime import UTC, date, datetime, timedelta

import jasil.runtime as platform_runtime
import pytest

import core.config as core_config
import core.date_range as core_date_range
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_poop.crud as poop_crud
import modules.health.health_poop.service as poop_service
import modules.health.health_sleep.crud as sleep_crud
import modules.health.health_steps.crud as steps_crud
import modules.health.health_steps.service as steps_service
import modules.health.health_water.crud as water_crud
import modules.health.health_weight.crud as weight_crud
from tests._factories import health as health_factories
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/health"
_BUCKET = health_constants.ChartBucket
_INTERVAL = health_constants.Interval
_SINCE = date(2026, 1, 1)


def _points(points) -> list[tuple[date, float]]:
    return [(point.date, point.value) for point in points]


def _at(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.fixture
def user(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def other(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def clock():
    """The platform clock, which the users' today is read from."""
    return platform_runtime.get_active_platform().clock


class TestChartBucketing:
    def test_a_chart_that_fits_stays_daily(self):
        asked = []

        def fetch(bucket):
            asked.append(bucket)
            return list(range(health_constants.MAX_CHART_POINTS))

        bucket, points = health_computation.chart_points(fetch)

        assert bucket is _BUCKET.DAY
        assert len(points) == health_constants.MAX_CHART_POINTS
        assert asked == [_BUCKET.DAY]

    def test_a_chart_that_does_not_fit_coarsens_until_it_does(self):
        sizes = {_BUCKET.DAY: 500, _BUCKET.WEEK: 72, _BUCKET.MONTH: 17}

        bucket, points = health_computation.chart_points(lambda b: list(range(sizes[b])))

        assert (bucket, len(points)) == (_BUCKET.WEEK, 72)

    def test_the_coarsest_bucket_is_used_whatever_its_size(self):
        sizes = {_BUCKET.DAY: 5000, _BUCKET.WEEK: 1500, _BUCKET.MONTH: 400}

        bucket, points = health_computation.chart_points(lambda b: list(range(sizes[b])))

        assert (bucket, len(points)) == (_BUCKET.MONTH, 400)

    @pytest.mark.parametrize(
        ("start", "bucket", "since", "today", "days"),
        [
            (date(2024, 3, 5), _BUCKET.DAY, date(2024, 1, 1), date(2024, 3, 9), 1),
            (date(2024, 3, 4), _BUCKET.WEEK, date(2023, 3, 1), date(2024, 3, 30), 7),
            (date(2024, 3, 4), _BUCKET.WEEK, date(2023, 3, 1), date(2024, 3, 6), 3),
            (date(2024, 2, 1), _BUCKET.MONTH, date(2024, 2, 20), date(2024, 6, 1), 10),
            (date(2024, 2, 1), _BUCKET.MONTH, date.min, date(2024, 6, 1), 29),
        ],
        ids=["day", "full-week", "current-week", "first-month", "full-month"],
    )
    def test_a_bucket_spans_the_days_it_has_inside_the_window(self, start, bucket, since, today, days):
        assert health_computation.bucket_day_count(start, bucket, since, today) == days


class TestAveragedCharts:
    def test_steps_average_per_day_week_and_month_for_the_user_only(self, db, user, other):
        # 2026-03-02 and 2026-03-04 share a week (Monday 2026-03-02); 2026-03-09 starts the next one.
        for day, steps in ((date(2026, 3, 2), 4000), (date(2026, 3, 4), 8000), (date(2026, 3, 9), 6000)):
            health_factories.make_health_steps(db, user.id, date=day, steps=steps)
        health_factories.make_health_steps(db, other.id, date=date(2026, 3, 2), steps=99999)

        assert _points(steps_crud.get_health_steps_chart(user.id, _SINCE, None, _BUCKET.DAY, db)) == [
            (date(2026, 3, 2), 4000.0),
            (date(2026, 3, 4), 8000.0),
            (date(2026, 3, 9), 6000.0),
        ]
        assert _points(steps_crud.get_health_steps_chart(user.id, _SINCE, None, _BUCKET.WEEK, db)) == [
            (date(2026, 3, 2), 6000.0),
            (date(2026, 3, 9), 6000.0),
        ]
        assert _points(steps_crud.get_health_steps_chart(user.id, _SINCE, None, _BUCKET.MONTH, db)) == [
            (date(2026, 3, 1), 6000.0)
        ]

    def test_no_records_is_an_empty_series(self, db, user):
        assert steps_crud.get_health_steps_chart(user.id, _SINCE, None, _BUCKET.DAY, db) == []

    def test_the_window_excludes_days_outside_it(self, db, user):
        for day in (date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 5)):
            health_factories.make_health_steps(db, user.id, date=day, steps=1000)

        assert _points(steps_crud.get_health_steps_chart(user.id, _SINCE, date(2026, 1, 4), _BUCKET.DAY, db)) == [
            (date(2026, 1, 1), 1000.0)
        ]
        assert len(steps_crud.get_health_steps_chart(user.id, date.min, None, _BUCKET.DAY, db)) == 3

    def test_the_bucket_the_window_opens_in_is_dated_the_window_start(self, db, user):
        # 2026-03-04 is a Wednesday: its week starts on Monday 03-02, before the window does.
        for day, steps in ((date(2026, 3, 3), 1000), (date(2026, 3, 4), 3000), (date(2026, 3, 9), 5000)):
            health_factories.make_health_steps(db, user.id, date=day, steps=steps)

        assert _points(steps_crud.get_health_steps_chart(user.id, date(2026, 3, 4), None, _BUCKET.WEEK, db)) == [
            (date(2026, 3, 4), 3000.0),
            (date(2026, 3, 9), 5000.0),
        ]
        assert _points(steps_crud.get_health_steps_chart(user.id, date(2026, 3, 4), None, _BUCKET.MONTH, db)) == [
            (date(2026, 3, 4), 4000.0)
        ]

    def test_weight_and_water_average_their_decimals(self, db, user):
        for day, kg, ml in ((2, 70.0, 1500), (3, 71.0, 2500)):
            health_factories.make_health_weight(db, user.id, date=date(2026, 3, day), weight_kg=kg)
            health_factories.make_health_water(db, user.id, date=date(2026, 3, day), amount_ml=ml)

        assert _points(weight_crud.get_health_weight_chart(user.id, _SINCE, None, _BUCKET.WEEK, db)) == [
            (date(2026, 3, 2), 70.5)
        ]
        assert _points(water_crud.get_health_water_chart(user.id, _SINCE, None, _BUCKET.WEEK, db)) == [
            (date(2026, 3, 2), 2000.0)
        ]

    def test_sleep_and_resting_heart_rate_skip_days_without_a_value(self, db, user):
        for day, seconds, rate in ((2, 28800, 50), (3, None, 54), (4, 21600, None)):
            health_factories.make_health_sleep(
                db, user.id, date=date(2026, 3, day), total_sleep_seconds=seconds, resting_heart_rate=rate
            )

        assert _points(sleep_crud.get_health_sleep_chart(user.id, _SINCE, None, _BUCKET.WEEK, db)) == [
            (date(2026, 3, 2), 25200.0)
        ]
        assert _points(
            sleep_crud.get_health_sleep_resting_heart_rate_chart(user.id, _SINCE, None, _BUCKET.WEEK, db)
        ) == [(date(2026, 3, 2), 52.0)]


class TestPoopCharts:
    def test_movements_are_counted_per_day_of_the_users_timezone(self, db, user, other):
        # 23:30 UTC on 2026-03-02 is already 2026-03-03 in Tokyo.
        for moment in (_at(2026, 3, 2, 23, 30), _at(2026, 3, 3, 1, 0), _at(2026, 3, 9, 12, 0)):
            health_factories.make_health_poop(db, user.id, date_time=moment)
        health_factories.make_health_poop(db, other.id, date_time=_at(2026, 3, 2, 12, 0))

        assert _points(poop_crud.get_health_poop_chart(user.id, _SINCE, None, _BUCKET.DAY, "UTC", db)) == [
            (date(2026, 3, 2), 1.0),
            (date(2026, 3, 3), 1.0),
            (date(2026, 3, 9), 1.0),
        ]
        assert _points(poop_crud.get_health_poop_chart(user.id, _SINCE, None, _BUCKET.DAY, "Asia/Tokyo", db)) == [
            (date(2026, 3, 3), 2.0),
            (date(2026, 3, 9), 1.0),
        ]
        assert _points(poop_crud.get_health_poop_chart(user.id, _SINCE, None, _BUCKET.MONTH, "UTC", db)) == [
            (date(2026, 3, 1), 3.0)
        ]

    def test_the_first_day_is_in_the_users_timezone(self, db, user, other):
        assert poop_crud.get_health_poop_first_day(user.id, "UTC", db) is None
        for moment in (_at(2026, 3, 2, 23, 30), _at(2026, 3, 9, 12, 0)):
            health_factories.make_health_poop(db, user.id, date_time=moment)
        health_factories.make_health_poop(db, other.id, date_time=_at(2025, 1, 1, 12, 0))

        assert poop_crud.get_health_poop_first_day(user.id, "UTC", db) == date(2026, 3, 2)
        assert poop_crud.get_health_poop_first_day(user.id, "Asia/Tokyo", db) == date(2026, 3, 3)

    def test_the_list_and_count_filter_on_the_users_local_day(self, db, user):
        # 23:30 UTC on 2026-03-02 is already 2026-03-03 in Tokyo, so a window opening on 03-03 includes it there.
        health_factories.make_health_poop(db, user.id, date_time=_at(2026, 3, 2, 23, 30))
        since = date(2026, 3, 3)

        assert poop_crud.get_health_poop_number_by_user_id(user.id, db, since, None, "Asia/Tokyo") == 1
        assert len(poop_crud.get_health_poop_by_user_id(user.id, db, 1, 10, since, None, "Asia/Tokyo")) == 1
        assert poop_crud.get_health_poop_number_by_user_id(user.id, db, since, None, "UTC") == 0
        assert poop_crud.get_health_poop_by_user_id(user.id, db, 1, 10, since, None, "UTC") == []


class TestIntervalCharts:
    def test_every_interval_charts_its_whole_range_daily_until_a_year_of_bars_is_exceeded(self, db, user, clock):
        """About 500 daily records: each interval covers its range, and all time is weekly."""
        clock.moment = _at(2026, 10, 28, 12)
        today = date(2026, 10, 28)
        for offset in range(500):
            health_factories.make_health_steps(db, user.id, date=today - timedelta(days=offset), steps=1000 + offset)

        series = {interval: steps_service.get_health_steps_chart(user.id, interval, db) for interval in _INTERVAL}

        assert {i: (s.bucket, len(s.points)) for i, s in series.items() if i is not _INTERVAL.ALL_TIME} == {
            _INTERVAL.LAST_7_DAYS: (_BUCKET.DAY, 8),
            _INTERVAL.LAST_30_DAYS: (_BUCKET.DAY, 31),
            _INTERVAL.LAST_90_DAYS: (_BUCKET.DAY, 91),
            _INTERVAL.LAST_YEAR: (_BUCKET.DAY, 366),
        }
        everything = series[_INTERVAL.ALL_TIME]
        assert everything.bucket is _BUCKET.WEEK
        assert 71 <= len(everything.points) <= 73

    def test_the_window_follows_the_users_timezone(self, db, clock):
        auckland = make_user(db, timezone="Pacific/Auckland")
        # 12:00 UTC on 31 March is already 1 April in Auckland.
        clock.moment = _at(2026, 3, 31, 12)
        health_factories.make_health_steps(db, auckland.id, date=date(2026, 3, 25), steps=1000)
        health_factories.make_health_steps(db, auckland.id, date=date(2026, 3, 24), steps=2000)

        series = steps_service.get_health_steps_chart(auckland.id, _INTERVAL.LAST_7_DAYS, db)

        assert _points(series.points) == [(date(2026, 3, 25), 1000.0)]

    def test_a_past_window_with_both_dates_charts_and_lists_the_same_days(self, db, user):
        for index, day in enumerate((date(2026, 1, 5), date(2026, 2, 10), date(2026, 2, 11), date(2026, 3, 20))):
            health_factories.make_health_steps(db, user.id, date=day, steps=1000 * (index + 1))
        window = core_date_range.DateRange(date(2026, 2, 10), date(2026, 2, 11))

        series = steps_service.get_health_steps_chart(user.id, _INTERVAL.LAST_7_DAYS, db, date_range=window)
        page = steps_service.list_health_steps(user.id, db, date_range=window)

        assert _points(series.points) == [(date(2026, 2, 10), 2000.0), (date(2026, 2, 11), 3000.0)]
        assert (page.total, sorted(item.steps for item in page.items)) == (2, [2000, 3000])


class TestPoopService:
    def test_each_point_is_the_movements_per_day_of_its_bucket(self, db, clock):
        """A year and more of daily movements is charted weekly; a week's value is its movements per day."""
        poop_user = make_user(db, timezone="UTC")
        clock.moment = _at(2026, 6, 12, 12)
        first = date(2025, 5, 5)  # a Monday
        for offset in range((date(2026, 6, 7) - first).days + 1):
            day = first + timedelta(days=offset)
            health_factories.make_health_poop(db, poop_user.id, date_time=_at(day.year, day.month, day.day, 9))
        for hour in (7, 8):
            health_factories.make_health_poop(db, poop_user.id, date_time=_at(2026, 6, 8, hour))
        health_factories.make_health_poop(db, poop_user.id, date_time=_at(2026, 6, 9, 7))

        series = poop_service.get_health_poop_chart(poop_user.id, _INTERVAL.ALL_TIME, db)

        assert series.bucket is _BUCKET.WEEK
        assert series.points[0].value == 1.0
        # The current week has had five days (Monday to Friday) and three movements on its first two.
        assert (series.points[-1].date, series.points[-1].value) == (date(2026, 6, 8), 0.6)

    def test_the_week_a_window_opens_in_counts_only_the_days_inside_the_window(self, db, clock):
        """The window opens on Thursday 2025-05-01: its first week holds four days, and four movements."""
        poop_user = make_user(db, timezone="UTC")
        clock.moment = _at(2026, 6, 12, 12)
        first = date(2025, 5, 1)
        for offset in range((date(2026, 6, 7) - first).days + 1):
            day = first + timedelta(days=offset)
            health_factories.make_health_poop(db, poop_user.id, date_time=_at(day.year, day.month, day.day, 9))

        series = poop_service.get_health_poop_chart(
            poop_user.id, _INTERVAL.ALL_TIME, db, date_range=core_date_range.DateRange(first, None)
        )

        assert series.bucket is _BUCKET.WEEK
        assert (series.points[0].date, series.points[0].value) == (first, 1.0)

    def test_a_daily_bucket_keeps_the_count(self, db, user, clock):
        clock.moment = _at(2026, 6, 12, 12)
        for hour in (7, 9):
            health_factories.make_health_poop(db, user.id, date_time=_at(2026, 6, 11, hour))

        series = poop_service.get_health_poop_chart(user.id, _INTERVAL.LAST_30_DAYS, db)

        assert _points(series.points) == [(date(2026, 6, 11), 2.0)]

    def test_all_time_starts_at_the_first_movement(self, db, user, clock):
        clock.moment = _at(2026, 6, 12, 12)
        health_factories.make_health_poop(db, user.id, date_time=_at(2024, 2, 20, 9))
        health_factories.make_health_poop(db, user.id, date_time=_at(2026, 6, 11, 9))

        series = poop_service.get_health_poop_chart(user.id, _INTERVAL.ALL_TIME, db)

        assert _points(series.points) == [(date(2024, 2, 20), 1.0), (date(2026, 6, 11), 1.0)]

    def test_all_time_without_movements_is_empty(self, db, user):
        assert poop_service.get_health_poop_chart(user.id, _INTERVAL.ALL_TIME, db).points == []

    def test_a_range_without_a_start_opens_at_the_first_movement(self, db, user, clock):
        clock.moment = _at(2024, 6, 12, 12)
        health_factories.make_health_poop(db, user.id, date_time=_at(2024, 2, 20, 9))
        health_factories.make_health_poop(db, user.id, date_time=_at(2024, 5, 1, 9))

        series = poop_service.get_health_poop_chart(
            user.id, _INTERVAL.LAST_7_DAYS, db, date_range=core_date_range.DateRange(None, date(2024, 4, 1))
        )

        assert _points(series.points) == [(date(2024, 2, 20), 1.0)]

    def test_the_earliest_allowed_time_is_charted_in_a_negative_offset_zone(self, db):
        """1900-01-01 00:30 UTC is 1899-12-31 in Los Angeles; the chart still finds it and buckets it."""
        angeleno = make_user(db, timezone="America/Los_Angeles")
        health_factories.make_health_poop(db, angeleno.id, date_time=_at(1900, 1, 1, 0, 30))
        health_factories.make_health_poop(db, angeleno.id, date_time=datetime.now(UTC) - timedelta(days=1))

        series = poop_service.get_health_poop_chart(angeleno.id, _INTERVAL.ALL_TIME, db)

        assert series.points[0].date == date(1899, 12, 31)
        assert len(series.points) == 2

    def test_a_window_is_the_users_local_days(self, db, clock):
        tokyo = make_user(db, timezone="Asia/Tokyo")
        clock.moment = _at(2026, 10, 28, 12)
        # Tokyo days: 03-01 21:00 -> 03-01, 03-03 08:30 -> 03-03, 03-04 00:30 -> 03-04, 03-09 21:00 -> 03-09.
        for moment in (_at(2026, 3, 1, 12), _at(2026, 3, 2, 23, 30), _at(2026, 3, 3, 15, 30), _at(2026, 3, 9, 12)):
            health_factories.make_health_poop(db, tokyo.id, date_time=moment)
        window = core_date_range.DateRange

        one_day = poop_service.list_health_poop(tokyo.id, db, date_range=window(date(2026, 3, 3), date(2026, 3, 3)))
        until = poop_service.list_health_poop(tokyo.id, db, date_range=window(None, date(2026, 3, 3)))
        after = poop_service.list_health_poop(tokyo.id, db, date_range=window(date(2026, 3, 4)))
        chart = poop_service.get_health_poop_chart(
            tokyo.id, _INTERVAL.LAST_7_DAYS, db, date_range=window(None, date(2026, 3, 3))
        )

        assert (one_day.total, until.total, after.total) == (1, 2, 2)
        assert poop_service.list_health_poop(tokyo.id, db).total == 4
        assert _points(chart.points) == [(date(2026, 3, 1), 1.0), (date(2026, 3, 3), 1.0)]


_ROUTES = [
    pytest.param("steps/chart", "steps", id="steps"),
    pytest.param("weight/chart", "weight_kg", id="weight"),
    pytest.param("water/chart", "amount_ml", id="water"),
    pytest.param("sleep/chart", "total_sleep_seconds", id="sleep"),
    pytest.param("sleep/chart/resting-heart-rate", "resting_heart_rate", id="resting-heart-rate"),
    pytest.param("poop/chart", None, id="poop"),
]


@pytest.fixture
def signed_user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, timezone="UTC")
        db.commit()
    return created


@pytest.fixture
def me(sign_in, signed_user):
    return sign_in(signed_user)


@pytest.fixture
def recent_records(committed_sessions, signed_user):
    """One record of every kind three days ago and one ten days ago, with a value for every chart."""
    today = platform_runtime.get_active_platform().clock.now().date()
    with committed_sessions() as db:
        for ago, value in ((3, 60), (10, 80)):
            day = today - timedelta(days=ago)
            noon = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
            health_factories.make_health_steps(db, signed_user.id, date=day, steps=value)
            health_factories.make_health_weight(db, signed_user.id, date=day, weight_kg=float(value))
            health_factories.make_health_water(db, signed_user.id, date=day, amount_ml=value)
            health_factories.make_health_sleep(
                db, signed_user.id, date=day, total_sleep_seconds=value, resting_heart_rate=value
            )
            health_factories.make_health_poop(db, signed_user.id, date_time=noon)
        db.commit()
    return today


@pytest.mark.parametrize(("route", "_column"), _ROUTES)
class TestChartRoutes:
    def test_the_series_is_the_buckets_with_a_value(self, me, recent_records, route, _column):
        response = me.client.get(f"{_URL}/{route}", params={"interval": "last_30_days"})

        assert response.status_code == 200
        body = response.json()
        assert body["bucket"] == "day"
        assert [p["date"] for p in body["points"]] == [
            (recent_records - timedelta(days=ago)).isoformat() for ago in (10, 3)
        ]

    def test_the_default_interval_is_the_last_seven_days(self, me, recent_records, route, _column):
        response = me.client.get(f"{_URL}/{route}")

        assert response.status_code == 200
        assert [p["date"] for p in response.json()["points"]] == [(recent_records - timedelta(days=3)).isoformat()]

    def test_an_unknown_interval_is_422(self, me, route, _column):
        assert me.client.get(f"{_URL}/{route}", params={"interval": "forever"}).status_code == 422

    def test_a_user_without_records_has_an_empty_series(self, me, route, _column):
        assert me.client.get(f"{_URL}/{route}").json() == {"bucket": "day", "points": []}


class TestChartRouteIsNotARecordId:
    def test_the_poop_chart_is_not_read_as_a_record_id(self, me, recent_records):
        response = me.client.get(f"{_URL}/poop/chart", params={"interval": "all_time"})

        assert response.status_code == 200
        assert len(response.json()["points"]) == 2
