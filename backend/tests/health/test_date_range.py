"""The optional ``start_date`` / ``end_date`` window every health list and chart accepts beside ``interval``."""

from datetime import UTC, date, datetime, timedelta

import pytest

import core.config as core_config
import core.date_range as core_date_range
import modules.health.computation as health_computation
import modules.health.constants as health_constants
from tests._factories import health as health_factories
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/health"
_INTERVAL = health_constants.Interval
_RANGE = core_date_range.DateRange
_DAYS = [date(2024, 1, 5), date(2024, 2, 10), date(2024, 2, 11), date(2024, 3, 20)]


def _noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, tzinfo=UTC)


def _fast(db, user_id, day):
    return health_factories.make_health_fasting(
        db, user_id, fast_start_time=_noon(day), fast_end_time=_noon(day) + timedelta(hours=10), status="completed"
    )


# kind -> (stage the record of a day, chart route or None)
_KINDS = {
    "steps": (lambda db, uid, day: health_factories.make_health_steps(db, uid, date=day), "steps/chart"),
    "weight": (lambda db, uid, day: health_factories.make_health_weight(db, uid, date=day), "weight/chart"),
    "water": (lambda db, uid, day: health_factories.make_health_water(db, uid, date=day), "water/chart"),
    "sleep": (lambda db, uid, day: health_factories.make_health_sleep(db, uid, date=day), "sleep/chart"),
    "poop": (lambda db, uid, day: health_factories.make_health_poop(db, uid, date_time=_noon(day)), "poop/chart"),
    "fasting": (_fast, None),
}
_CHARTED = [pytest.param(kind, id=kind) for kind, (_, chart) in _KINDS.items() if chart]


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, timezone="UTC")
        db.commit()
    return created


@pytest.fixture
def me(sign_in, user):
    return sign_in(user)


@pytest.fixture
def records(committed_sessions, user):
    """Stage one record per day of :data:`_DAYS` for every kind; return ``{kind: {day: id}}``."""
    staged: dict[str, dict[date, str]] = {}
    with committed_sessions() as db:
        for kind, (stage, _) in _KINDS.items():
            staged[kind] = {day: str(stage(db, user.id, day).id) for day in _DAYS}
        db.commit()
    return staged


def _listed(me, kind: str, **params) -> list[str]:
    response = me.client.get(f"{_URL}/{kind}", params={"num_records": 100, **params})
    assert response.status_code == 200
    return [item["id"] for item in response.json()["items"]]


@pytest.mark.parametrize("kind", list(_KINDS))
class TestList:
    def test_both_dates_bound_the_list_inclusively(self, me, records, kind):
        ids = records[kind]

        listed = _listed(me, kind, start_date="2024-02-10", end_date="2024-03-20")

        assert listed == [ids[_DAYS[3]], ids[_DAYS[2]], ids[_DAYS[1]]]

    def test_one_date_leaves_the_other_end_open(self, me, records, kind):
        ids = records[kind]

        assert _listed(me, kind, start_date="2024-02-11") == [ids[_DAYS[3]], ids[_DAYS[2]]]
        assert _listed(me, kind, end_date="2024-02-10") == [ids[_DAYS[1]], ids[_DAYS[0]]]

    def test_a_single_day_is_start_equal_to_end(self, me, records, kind):
        assert _listed(me, kind, start_date="2024-02-10", end_date="2024-02-10") == [records[kind][_DAYS[1]]]

    def test_the_total_counts_the_window_not_the_page(self, me, records, kind):
        response = me.client.get(
            f"{_URL}/{kind}", params={"start_date": "2024-01-01", "end_date": "2024-02-28", "num_records": 1}
        )

        body = response.json()
        assert (body["total"], len(body["items"]), body["next"]) == (3, 1, 2)

    def test_the_dates_replace_the_interval(self, me, records, kind):
        listed = _listed(me, kind, interval="last_7_days", start_date="2024-01-01", end_date="2024-01-31")

        assert listed == [records[kind][_DAYS[0]]]

    def test_an_interval_alone_looks_back_from_today(self, me, records, kind):
        assert _listed(me, kind, interval="last_7_days") == []
        assert len(_listed(me, kind, interval="all_time")) == len(_DAYS)

    def test_a_start_after_the_end_is_422_naming_the_end(self, me, kind):
        response = me.client.get(f"{_URL}/{kind}", params={"start_date": "2024-02-10", "end_date": "2024-01-05"})

        assert response.status_code == 422
        body = response.json()
        assert body["type"].endswith("validation-failed")
        assert body["errors"][0]["field"] == "query.end_date"

    def test_a_malformed_date_is_422(self, me, kind):
        assert me.client.get(f"{_URL}/{kind}", params={"start_date": "yesterday"}).status_code == 422


@pytest.mark.parametrize("kind", _CHARTED)
class TestChart:
    @staticmethod
    def _points(me, kind: str, **params) -> list[str]:
        response = me.client.get(f"{_URL}/{_KINDS[kind][1]}", params=params)
        assert response.status_code == 200
        return [point["date"] for point in response.json()["points"]]

    def test_both_dates_bound_the_chart(self, me, records, kind):
        assert self._points(me, kind, start_date="2024-02-10", end_date="2024-02-11") == ["2024-02-10", "2024-02-11"]

    def test_a_single_day_is_start_equal_to_end(self, me, records, kind):
        assert self._points(me, kind, start_date="2024-02-11", end_date="2024-02-11") == ["2024-02-11"]

    def test_one_date_leaves_the_other_end_open(self, me, records, kind):
        assert self._points(me, kind, start_date="2024-02-11") == ["2024-02-11", "2024-03-20"]
        assert self._points(me, kind, end_date="2024-02-10") == ["2024-01-05", "2024-02-10"]

    def test_the_dates_replace_the_interval(self, me, records, kind):
        assert self._points(me, kind, interval="last_7_days", start_date="2024-01-01", end_date="2024-01-31") == [
            "2024-01-05"
        ]

    def test_a_start_after_the_end_is_422_naming_the_end(self, me, kind):
        response = me.client.get(
            f"{_URL}/{_KINDS[kind][1]}", params={"start_date": "2024-02-10", "end_date": "2024-01-05"}
        )

        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "query.end_date"

    def test_a_malformed_date_is_422(self, me, kind):
        assert me.client.get(f"{_URL}/{_KINDS[kind][1]}", params={"end_date": "soon"}).status_code == 422


class TestWindowBounds:
    TODAY = date(2026, 3, 31)

    def test_an_interval_alone_opens_at_its_start_with_no_end(self):
        bounds = health_computation.window_bounds(_INTERVAL.LAST_30_DAYS, _RANGE(), lambda: self.TODAY)

        assert bounds == (date(2026, 3, 1), None)

    def test_nothing_is_unbounded_and_never_reads_the_clock(self):
        def fail() -> date:
            raise AssertionError("today must not be read")

        assert health_computation.window_bounds(None, _RANGE(), fail) == (None, None)

    def test_dates_replace_the_interval_and_never_read_the_clock(self):
        def fail() -> date:
            raise AssertionError("today must not be read")

        window = _RANGE(date(2023, 1, 1), date(2023, 1, 31))

        assert health_computation.window_bounds(_INTERVAL.LAST_7_DAYS, window, fail) == (
            date(2023, 1, 1),
            date(2023, 1, 31),
        )

    def test_an_end_alone_has_no_start_whatever_the_interval(self):
        bounds = health_computation.window_bounds(
            _INTERVAL.LAST_7_DAYS, _RANGE(None, date(2023, 1, 31)), lambda: self.TODAY
        )

        assert bounds == (None, date(2023, 1, 31))
