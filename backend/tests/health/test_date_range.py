"""The optional ``start_date`` / ``end_date`` window every health list and chart accepts beside ``interval``."""

import importlib
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

import core.database as core_database
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.dependencies as auth_dependencies
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.service as health_poop_service
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_weight.crud as health_weight_crud
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema

_HEADERS = {"Authorization": "Bearer mock_token"}
_LOCAL_TODAY = "modules.users.users.integration_service.local_today"
_RESOLVE_TIMEZONE = "modules.users.users.integration_service.resolve_timezone"
_INTERVAL = health_constants.Interval
_BUCKET = health_constants.ChartBucket
_RANGE = health_computation.DateRange
_NO_RANGE = _RANGE()

_PACKAGES = ["steps", "weight", "water", "sleep", "poop", "fasting"]
# (route, service function the route calls)
_LISTS = [pytest.param(f"/health_{name}", f"list_health_{name}", id=f"list-{name}") for name in _PACKAGES]
_CHARTS = [
    pytest.param(f"/health_{name}/chart", f"get_health_{name}_chart", id=f"chart-{name}")
    for name in ("steps", "weight", "water", "sleep", "poop")
] + [
    pytest.param("/health_sleep/chart/resting-heart-rate", "get_health_sleep_resting_heart_rate_chart", id="chart-rhr")
]


def _client(mock_db, route: str) -> tuple[TestClient, str]:
    """Mount the one health router ``route`` belongs to, with auth and the session stubbed."""
    package = route.split("/")[1]
    router = importlib.import_module(f"modules.health.{package}.router")
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix=f"/{package}")
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    return TestClient(app), f"modules.health.{package}.router.{package}_service"


def _sql(mock_db) -> str:
    return str(
        mock_db.execute.call_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def _called_with_range(route: str, function: str, query: str, mock_db) -> tuple[int, MagicMock]:
    client, service = _client(mock_db, route)
    returned = (
        core_pagination.Page(items=[], total=0, page=1, num_records=25)
        if "chart" not in route
        else health_schema.HealthChartSeries(bucket=_BUCKET.DAY, points=[])
    )
    with patch(f"{service}.{function}", return_value=returned) as mock_service:
        response = client.get(f"{route}?{query}", headers=_HEADERS)
    return response.status_code, mock_service


def _range_argument(route: str, mock_service: MagicMock) -> health_computation.DateRange:
    return mock_service.call_args.kwargs["date_range"]


@pytest.mark.parametrize(("route", "function"), _LISTS + _CHARTS)
class TestRoutes:
    def test_passes_both_dates_through(self, route, function, mock_db):
        status, mock_service = _called_with_range(route, function, "start_date=2024-01-05&end_date=2024-02-10", mock_db)

        assert status == 200
        assert _range_argument(route, mock_service) == _RANGE(date(2024, 1, 5), date(2024, 2, 10))

    def test_one_date_leaves_the_other_open(self, route, function, mock_db):
        _, only_start = _called_with_range(route, function, "start_date=2024-01-05", mock_db)
        _, only_end = _called_with_range(route, function, "end_date=2024-02-10", mock_db)

        assert _range_argument(route, only_start) == _RANGE(date(2024, 1, 5), None)
        assert _range_argument(route, only_end) == _RANGE(None, date(2024, 2, 10))

    def test_a_single_day_is_start_equal_to_end(self, route, function, mock_db):
        status, mock_service = _called_with_range(route, function, "start_date=2024-01-05&end_date=2024-01-05", mock_db)

        assert status == 200
        assert _range_argument(route, mock_service) == _RANGE(date(2024, 1, 5), date(2024, 1, 5))

    def test_no_dates_is_the_unchanged_default(self, route, function, mock_db):
        status, mock_service = _called_with_range(route, function, "interval=last_30_days", mock_db)

        assert status == 200
        assert _range_argument(route, mock_service) == _NO_RANGE

    def test_a_start_after_the_end_is_422(self, route, function, mock_db):
        client, service = _client(mock_db, route)
        with patch(f"{service}.{function}") as mock_service:
            response = client.get(f"{route}?start_date=2024-02-10&end_date=2024-01-05", headers=_HEADERS)

        assert response.status_code == 422
        body = response.json()
        assert body["type"].endswith("validation-failed")
        assert body["errors"][0]["field"] == "query.end_date"
        mock_service.assert_not_called()

    def test_a_malformed_date_is_422(self, route, function, mock_db):
        client, _ = _client(mock_db, route)

        assert client.get(f"{route}?start_date=yesterday", headers=_HEADERS).status_code == 422


class TestWindowBounds:
    TODAY = date(2026, 3, 31)

    def test_an_interval_alone_opens_at_its_start_with_no_end(self):
        assert health_computation.window_bounds(_INTERVAL.LAST_30_DAYS, _NO_RANGE, lambda: self.TODAY) == (
            date(2026, 3, 1),
            None,
        )

    def test_nothing_is_unbounded_and_never_reads_the_clock(self):
        today = MagicMock()

        assert health_computation.window_bounds(None, _NO_RANGE, today) == (None, None)
        today.assert_not_called()

    def test_dates_replace_the_interval(self):
        today = MagicMock()

        bounds = health_computation.window_bounds(
            _INTERVAL.LAST_7_DAYS, _RANGE(date(2023, 1, 1), date(2023, 1, 31)), today
        )

        assert bounds == (date(2023, 1, 1), date(2023, 1, 31))
        today.assert_not_called()

    def test_an_end_alone_has_no_start_whatever_the_interval(self):
        assert health_computation.window_bounds(
            _INTERVAL.LAST_7_DAYS, _RANGE(None, date(2023, 1, 31)), lambda: self.TODAY
        ) == (
            None,
            date(2023, 1, 31),
        )


class TestRecordService:
    @patch(_LOCAL_TODAY, return_value=date(2026, 3, 31))
    def test_a_list_counts_and_fetches_the_range_not_the_interval(self, _today, mock_db):
        count = MagicMock(return_value=0)
        fetch = MagicMock(return_value=[])

        health_record_service.list_page(
            1, _INTERVAL.LAST_7_DAYS, _RANGE(date(2023, 1, 1), date(2023, 1, 31)), 1, 25, count, fetch, mock_db
        )

        count.assert_called_once_with(date(2023, 1, 1), date(2023, 1, 31))
        fetch.assert_called_once_with(date(2023, 1, 1), date(2023, 1, 31))

    @patch(_LOCAL_TODAY, return_value=date(2026, 3, 31))
    def test_a_chart_fetches_the_range_not_the_interval(self, _today, mock_db):
        fetch = MagicMock(return_value=[])

        health_record_service.chart(
            1, _INTERVAL.LAST_7_DAYS, _RANGE(date(2023, 1, 1), date(2023, 1, 31)), fetch, mock_db
        )

        fetch.assert_called_once_with(date(2023, 1, 1), date(2023, 1, 31), _BUCKET.DAY)

    @patch(_LOCAL_TODAY, return_value=date(2026, 3, 31))
    def test_a_chart_with_only_an_end_opens_at_the_earliest_date(self, _today, mock_db):
        fetch = MagicMock(return_value=[])

        health_record_service.chart(1, _INTERVAL.LAST_7_DAYS, _RANGE(None, date(2023, 1, 31)), fetch, mock_db)

        fetch.assert_called_once_with(date.min, date(2023, 1, 31), _BUCKET.DAY)


class TestCrud:
    def test_a_count_is_bounded_on_both_sides(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 3

        health_steps_crud.get_health_steps_number_by_user_id(1, mock_db, date(2024, 1, 5), date(2024, 2, 10))

        sql = _sql(mock_db)
        assert "health_steps.date >= '2024-01-05'" in sql
        assert "health_steps.date <= '2024-02-10'" in sql

    def test_a_list_is_bounded_on_both_sides(self, mock_db):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        health_weight_crud.get_health_weight_by_user_id(1, mock_db, None, None, date(2024, 1, 5), date(2024, 2, 10))

        sql = _sql(mock_db)
        assert "health_weight.date >= '2024-01-05'" in sql
        assert "health_weight.date <= '2024-02-10'" in sql

    def test_an_open_end_adds_no_upper_bound(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 3

        health_steps_crud.get_health_steps_number_by_user_id(1, mock_db, date(2024, 1, 5))

        assert "<=" not in _sql(mock_db)

    def test_a_fasting_session_is_filed_under_the_day_it_started(self, mock_db):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        health_fasting_crud.get_health_fasting_by_user_id(1, mock_db, None, None, date(2024, 1, 5), date(2024, 2, 10))

        sql = _sql(mock_db)
        assert "CAST(health_fasting.fast_start_time AS DATE) <= '2024-02-10'" in sql

    def test_a_poop_list_bounds_the_users_local_day(self, mock_db):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        health_poop_crud.get_health_poop_by_user_id(
            1, mock_db, None, None, date(2024, 1, 5), date(2024, 2, 10), "Asia/Tokyo"
        )

        sql = _sql(mock_db)
        assert "Asia/Tokyo" in sql
        assert "<= '2024-02-10'" in sql

    def test_a_chart_is_bounded_on_both_sides(self, mock_db):
        mock_db.execute.return_value.all.return_value = []

        health_steps_crud.get_health_steps_chart(1, date(2024, 1, 5), date(2024, 2, 10), _BUCKET.DAY, mock_db)

        sql = _sql(mock_db)
        assert "health_steps.date >= '2024-01-05'" in sql
        assert "health_steps.date <= '2024-02-10'" in sql


class TestPoopChart:
    @patch(_RESOLVE_TIMEZONE, return_value="UTC")
    @patch(_LOCAL_TODAY, return_value=date(2024, 6, 12))
    @patch(
        "modules.health.health_poop.service.health_poop_crud.get_health_poop_first_day", return_value=date(2024, 2, 20)
    )
    @patch("modules.health.health_poop.service.health_poop_crud.get_health_poop_chart")
    def test_a_range_without_a_start_opens_at_the_first_movement(self, mock_crud, _first, _today, _tz, mock_db):
        mock_crud.return_value = []

        health_poop_service.get_health_poop_chart(
            1, _INTERVAL.LAST_7_DAYS, mock_db, date_range=_RANGE(None, date(2024, 4, 1))
        )

        mock_crud.assert_called_once_with(1, date(2024, 2, 20), date(2024, 4, 1), _BUCKET.DAY, "UTC", mock_db)

    @patch(_RESOLVE_TIMEZONE, return_value="UTC")
    @patch(_LOCAL_TODAY, return_value=date(2024, 6, 12))
    @patch("modules.health.health_poop.service.health_poop_crud.get_health_poop_chart")
    def test_a_past_window_averages_over_its_own_days_not_up_to_today(self, mock_crud, _today, _tz, mock_db):
        weekly = [health_schema.HealthChartPoint(date=date(2024, 3, 25), value=7.0)]
        too_many = [health_schema.HealthChartPoint(date=date(2024, 3, 25), value=1.0)] * 400
        mock_crud.side_effect = lambda _user, _since, _until, bucket, _tz, _db: (
            too_many if bucket is _BUCKET.DAY else weekly
        )

        # The window closes on Wed 2024-03-27, so the week of the 25th spans 3 of its days: 7 / 3.
        series = health_poop_service.get_health_poop_chart(
            1, _INTERVAL.LAST_7_DAYS, mock_db, date_range=_RANGE(date(2024, 1, 1), date(2024, 3, 27))
        )

        assert [point.value for point in series.points] == [2.33]
