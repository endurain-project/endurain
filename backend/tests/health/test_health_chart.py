"""The aggregated chart series every health metric serves beside its paginated list."""

import importlib
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_dependencies
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.service as health_poop_service
import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.service as health_sleep_service
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.service as health_steps_service
import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.service as health_water_service
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.service as health_weight_service
import modules.health.schema as health_schema

_HEADERS = {"Authorization": "Bearer mock_token"}
_BUCKET = health_constants.ChartBucket
_INTERVAL = health_constants.Interval
_LOCAL_TODAY = "modules.users.users.integration_service.local_today"
_RESOLVE_TIMEZONE = "modules.users.users.integration_service.resolve_timezone"

# (crud module, service module, route, chart function, aggregated column)
_AVERAGED = [
    pytest.param(
        health_steps_crud, health_steps_service, "/health_steps/chart", "get_health_steps_chart", "health_steps.steps"
    ),
    pytest.param(
        health_weight_crud,
        health_weight_service,
        "/health_weight/chart",
        "get_health_weight_chart",
        "health_weight.weight",
    ),
    pytest.param(
        health_water_crud,
        health_water_service,
        "/health_water/chart",
        "get_health_water_chart",
        "health_water.amount_ml",
    ),
    pytest.param(
        health_sleep_crud,
        health_sleep_service,
        "/health_sleep/chart",
        "get_health_sleep_chart",
        "health_sleep.total_sleep_seconds",
    ),
    pytest.param(
        health_sleep_crud,
        health_sleep_service,
        "/health_sleep/chart/resting-heart-rate",
        "get_health_sleep_resting_heart_rate_chart",
        "health_sleep.resting_heart_rate",
    ),
]


def _client(mock_db, route: str) -> TestClient:
    """Mount the one health router ``route`` belongs to, with auth and the session stubbed."""
    package = route.split("/")[1]
    router = importlib.import_module(f"modules.health.{package}.router")
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix=f"/{package}")
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    return TestClient(app)


def _sql(mock_db) -> str:
    return str(
        mock_db.execute.call_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


class TestChartBucketing:
    def test_a_chart_that_fits_stays_daily(self):
        fetch = MagicMock(return_value=list(range(health_constants.MAX_CHART_POINTS)))

        bucket, points = health_computation.chart_points(fetch)

        assert bucket is _BUCKET.DAY
        assert len(points) == health_constants.MAX_CHART_POINTS
        fetch.assert_called_once_with(_BUCKET.DAY)

    def test_a_chart_that_does_not_fit_coarsens_until_it_does(self):
        sizes = {_BUCKET.DAY: 500, _BUCKET.WEEK: 72, _BUCKET.MONTH: 17}

        bucket, points = health_computation.chart_points(lambda b: list(range(sizes[b])))

        assert (bucket, len(points)) == (_BUCKET.WEEK, 72)

    def test_the_coarsest_bucket_is_used_whatever_its_size(self):
        sizes = {_BUCKET.DAY: 5000, _BUCKET.WEEK: 1500, _BUCKET.MONTH: 400}

        bucket, points = health_computation.chart_points(lambda b: list(range(sizes[b])))

        assert (bucket, len(points)) == (_BUCKET.MONTH, 400)

    def test_a_day_bucket_spans_one_day(self):
        assert (
            health_computation.bucket_day_count(date(2024, 3, 5), _BUCKET.DAY, date(2024, 1, 1), date(2024, 3, 9)) == 1
        )

    def test_a_full_week_spans_seven_days(self):
        assert (
            health_computation.bucket_day_count(date(2024, 3, 4), _BUCKET.WEEK, date(2023, 3, 1), date(2024, 3, 30))
            == 7
        )

    def test_the_current_week_stops_at_today(self):
        assert (
            health_computation.bucket_day_count(date(2024, 3, 4), _BUCKET.WEEK, date(2023, 3, 1), date(2024, 3, 6)) == 3
        )

    def test_the_first_month_starts_at_the_window(self):
        assert (
            health_computation.bucket_day_count(date(2024, 2, 1), _BUCKET.MONTH, date(2024, 2, 20), date(2024, 6, 1))
            == 10
        )

    def test_a_full_month_spans_its_days(self):
        assert health_computation.bucket_day_count(date(2024, 2, 1), _BUCKET.MONTH, date.min, date(2024, 6, 1)) == 29

    def test_the_bucket_expression_truncates_to_the_bucket(self):
        expression = health_computation.chart_bucket_expression(
            health_steps_crud.health_steps_models.HealthSteps.date, _BUCKET.WEEK, date(2024, 1, 1)
        )

        sql = str(expression.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert "date_trunc('week'" in sql
        assert "greatest(" in sql


@pytest.mark.parametrize(("crud", "service", "route", "function", "column"), _AVERAGED)
class TestAveragedCrud:
    def test_averages_the_column_per_bucket(self, crud, service, route, function, column, mock_db):
        mock_db.execute.return_value.all.return_value = [(date(2024, 1, 1), 10.5), (date(2024, 1, 8), 20)]

        points = getattr(crud, function)(1, date(2023, 1, 1), _BUCKET.WEEK, mock_db)

        assert points == [
            health_schema.HealthChartPoint(date=date(2024, 1, 1), value=10.5),
            health_schema.HealthChartPoint(date=date(2024, 1, 8), value=20.0),
        ]
        sql = _sql(mock_db)
        assert f"avg({column})" in sql
        assert "date_trunc('week'" in sql
        assert f"{column} IS NOT NULL" in sql
        assert "user_id = 1" in sql
        assert "'2023-01-01'" in sql
        assert "GROUP BY" in sql

    def test_no_records_is_an_empty_series(self, crud, service, route, function, column, mock_db):
        mock_db.execute.return_value.all.return_value = []

        assert getattr(crud, function)(1, date(2023, 1, 1), _BUCKET.DAY, mock_db) == []


@pytest.mark.parametrize(("crud", "service", "route", "function", "column"), _AVERAGED)
class TestAveragedService:
    @patch(_LOCAL_TODAY, return_value=date(2024, 6, 1))
    def test_charts_the_intervals_window_in_its_bucket(self, _today, crud, service, route, function, column, mock_db):
        points = [health_schema.HealthChartPoint(date=date(2024, 1, 1), value=3.0)]
        with patch.object(crud, function, return_value=points) as mock_crud:
            series = getattr(service, function)(1, _INTERVAL.LAST_YEAR, mock_db)

        mock_crud.assert_called_once_with(1, date(2023, 6, 2), _BUCKET.DAY, mock_db)
        assert series == health_schema.HealthChartSeries(bucket=_BUCKET.DAY, points=points)


@pytest.mark.parametrize(("crud", "service", "route", "function", "column"), _AVERAGED)
class TestAveragedRouter:
    def test_returns_the_series(self, crud, service, route, function, column, mock_db):
        series = health_schema.HealthChartSeries(
            bucket=_BUCKET.DAY, points=[health_schema.HealthChartPoint(date=date(2024, 1, 1), value=3.0)]
        )
        with patch.object(service, function, return_value=series) as mock_service:
            response = _client(mock_db, route).get(f"{route}?interval=last_30_days", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json() == {"bucket": "day", "points": [{"date": "2024-01-01", "value": 3.0}]}
        assert mock_service.call_args.args[0] == 1
        assert mock_service.call_args.args[1] is _INTERVAL.LAST_30_DAYS

    def test_defaults_to_the_last_seven_days(self, crud, service, route, function, column, mock_db):
        with patch.object(
            service, function, return_value=health_schema.HealthChartSeries(bucket=_BUCKET.DAY, points=[])
        ) as mock_service:
            response = _client(mock_db, route).get(route, headers=_HEADERS)

        assert response.status_code == 200
        assert mock_service.call_args.args[1] is _INTERVAL.LAST_7_DAYS

    def test_rejects_an_unknown_interval(self, crud, service, route, function, column, mock_db):
        assert _client(mock_db, route).get(f"{route}?interval=forever", headers=_HEADERS).status_code == 422


class TestPoopCrud:
    def test_counts_movements_per_local_bucket(self, mock_db):
        mock_db.execute.return_value.all.return_value = [(date(2024, 1, 1), 9)]

        points = health_poop_crud.get_health_poop_chart(1, date(2023, 1, 1), _BUCKET.MONTH, "Asia/Tokyo", mock_db)

        assert points == [health_schema.HealthChartPoint(date=date(2024, 1, 1), value=9.0)]
        sql = _sql(mock_db)
        assert "count(*)" in sql
        assert "Asia/Tokyo" in sql
        assert "date_trunc('month'" in sql
        assert "user_id = 1" in sql


class TestPoopService:
    @patch(_RESOLVE_TIMEZONE, return_value="UTC")
    @patch(_LOCAL_TODAY, return_value=date(2024, 6, 12))
    @patch("modules.health.health_poop.service.health_poop_crud.get_health_poop_first_day", return_value=None)
    @patch("modules.health.health_poop.service.health_poop_crud.get_health_poop_chart")
    def test_reports_movements_per_day_of_each_bucket(self, mock_crud, _first, _today, _tz, mock_db):
        weekly = [
            health_schema.HealthChartPoint(date=date(2024, 6, 3), value=14.0),
            health_schema.HealthChartPoint(date=date(2024, 6, 10), value=3.0),
        ]
        too_many_days = [health_schema.HealthChartPoint(date=date(2024, 6, 1), value=1.0)] * 400
        mock_crud.side_effect = lambda _user, _since, bucket, _tz, _db: (
            too_many_days if bucket is _BUCKET.DAY else weekly
        )

        series = health_poop_service.get_health_poop_chart(1, _INTERVAL.ALL_TIME, mock_db)

        assert series.bucket is _BUCKET.WEEK
        # A full week of 14 movements is 2 a day; the current week has 3 days so far.
        assert [point.value for point in series.points] == [2.0, 1.0]

    @patch(_RESOLVE_TIMEZONE, return_value="UTC")
    @patch(_LOCAL_TODAY, return_value=date(2024, 6, 12))
    @patch("modules.health.health_poop.service.health_poop_crud.get_health_poop_chart")
    def test_a_daily_bucket_keeps_the_count(self, mock_crud, _today, _tz, mock_db):
        mock_crud.return_value = [health_schema.HealthChartPoint(date=date(2024, 6, 11), value=2.0)]

        series = health_poop_service.get_health_poop_chart(1, _INTERVAL.LAST_30_DAYS, mock_db)

        assert [point.value for point in series.points] == [2.0]

    @patch(_RESOLVE_TIMEZONE, return_value="UTC")
    @patch(_LOCAL_TODAY, return_value=date(2024, 6, 12))
    @patch(
        "modules.health.health_poop.service.health_poop_crud.get_health_poop_first_day", return_value=date(2024, 2, 20)
    )
    @patch("modules.health.health_poop.service.health_poop_crud.get_health_poop_chart")
    def test_all_time_starts_the_first_month_at_the_first_movement(self, mock_crud, _first, _today, _tz, mock_db):
        monthly = [
            health_schema.HealthChartPoint(date=date(2024, 2, 1), value=10.0),
            health_schema.HealthChartPoint(date=date(2024, 3, 1), value=31.0),
        ]
        too_many = [health_schema.HealthChartPoint(date=date(2024, 2, 1), value=1.0)] * 400
        mock_crud.side_effect = lambda _user, _since, bucket, _tz, _db: monthly if bucket is _BUCKET.MONTH else too_many

        series = health_poop_service.get_health_poop_chart(1, _INTERVAL.ALL_TIME, mock_db)

        mock_crud.assert_any_call(1, date(2024, 2, 20), _BUCKET.MONTH, "UTC", mock_db)
        # February counts only its 10 days from the 20th; March is a full month.
        assert [point.value for point in series.points] == [1.0, 1.0]

    @patch(_RESOLVE_TIMEZONE, return_value="UTC")
    @patch(_LOCAL_TODAY, return_value=date(2024, 6, 12))
    @patch("modules.health.health_poop.service.health_poop_crud.get_health_poop_first_day", return_value=None)
    @patch("modules.health.health_poop.service.health_poop_crud.get_health_poop_chart", return_value=[])
    def test_all_time_without_movements_is_empty(self, _crud, _first, _today, _tz, mock_db):
        assert health_poop_service.get_health_poop_chart(1, _INTERVAL.ALL_TIME, mock_db).points == []


class TestPoopRouter:
    def test_chart_is_not_read_as_a_record_id(self, mock_db):
        series = health_schema.HealthChartSeries(bucket=_BUCKET.DAY, points=[])
        with patch(
            "modules.health.health_poop.router.health_poop_service.get_health_poop_chart", return_value=series
        ) as mock_service:
            response = _client(mock_db, "/health_poop/chart").get(
                "/health_poop/chart?interval=all_time", headers=_HEADERS
            )

        assert response.status_code == 200
        assert mock_service.call_args.args[1] is _INTERVAL.ALL_TIME
