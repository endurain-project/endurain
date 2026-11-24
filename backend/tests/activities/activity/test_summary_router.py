"""The activity summaries through the production application: the period, the anchor day and the user's own week."""

from datetime import UTC, datetime, timedelta

import jasil.runtime as jasil_runtime
import pytest

import core.config as core_config
from tests._factories.activities import make_activity_at
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/activities/summaries"
_DAY = datetime(2026, 7, 15, 9, tzinfo=UTC)  # a Wednesday


class TestWeek:
    def test_the_week_holding_the_date_is_totalled_per_day_and_per_type(self, me, owner, arrange):
        arrange(
            lambda db: (
                make_activity_at(
                    db, owner.id, _DAY, distance=10000, total_timer_time=3000.0, elevation_gain=100, calories=500
                ),
                make_activity_at(db, owner.id, _DAY + timedelta(hours=5), activity_type=4, distance=40000),
                make_activity_at(db, owner.id, _DAY - timedelta(days=7), distance=999),
            )
        )

        body = me.client.get(_URL, params={"period": "week", "date": "2026-07-16"}).json()

        assert (body["activity_count"], body["total_distance"], body["total_elevation_gain"]) == (2, 50000.0, 100.0)
        assert body["total_calories"] == 500.0
        assert {day["day_of_week"]: day["activity_count"] for day in body["breakdown"]}[2] == 2
        assert {item["activity_type"]: item["activity_count"] for item in body["type_breakdown"]} == {
            "run": 1,
            "ride": 1,
        }

    def test_the_week_is_the_default_period_and_the_clock_gives_the_users_today(self, me, owner, arrange):
        jasil_runtime.get_active_platform().clock.moment = _DAY
        arrange(lambda db: make_activity_at(db, owner.id, _DAY - timedelta(hours=3), distance=1234))

        body = me.client.get(_URL).json()

        assert (body["activity_count"], body["total_distance"]) == (1, 1234.0)
        assert len(body["breakdown"]) == 7

    def test_a_week_opens_on_the_users_first_day_of_the_week(self, sign_in, arrange):
        sunday_first = arrange(lambda db: make_user(db, timezone="UTC", first_day_of_week="sunday"))
        arrange(lambda db: make_activity_at(db, sunday_first.id, datetime(2026, 7, 12, 10, tzinfo=UTC)))

        body = sign_in(sunday_first).client.get(_URL, params={"date": "2026-07-15"}).json()

        assert body["activity_count"] == 1

    def test_the_type_filter_keeps_the_type_asked_for(self, me, owner, arrange):
        arrange(
            lambda db: (
                make_activity_at(db, owner.id, _DAY, distance=1000),
                make_activity_at(db, owner.id, _DAY + timedelta(hours=4), activity_type=4, distance=5000),
            )
        )

        body = me.client.get(_URL, params={"date": "2026-07-15", "type": "ride"}).json()

        assert (body["activity_count"], body["total_distance"]) == (1, 5000.0)

    def test_another_users_activities_are_not_summarised(self, me, other, arrange):
        arrange(lambda db: make_activity_at(db, other.id, _DAY))

        assert me.client.get(_URL, params={"date": "2026-07-15"}).json()["activity_count"] == 0


class TestMonthYearAndLifetime:
    @pytest.fixture(autouse=True)
    def _activities(self, owner, arrange):
        arrange(
            lambda db: (
                make_activity_at(db, owner.id, _DAY, distance=1000, timezone="UTC"),
                make_activity_at(db, owner.id, datetime(2026, 2, 3, 9, tzinfo=UTC), distance=2000),
                make_activity_at(db, owner.id, datetime(2025, 5, 3, 9, tzinfo=UTC), distance=4000),
            )
        )

    def test_the_month_holding_the_date(self, me):
        body = me.client.get(_URL, params={"period": "month", "date": "2026-07-31"}).json()

        assert (body["activity_count"], body["total_distance"]) == (1, 1000.0)

    def test_the_year_asked_for_with_its_months(self, me):
        body = me.client.get(_URL, params={"period": "year", "year": 2026}).json()

        assert (body["activity_count"], body["total_distance"]) == (2, 3000.0)
        assert {m["month_number"]: m["activity_count"] for m in body["breakdown"] if m["activity_count"]} == {
            2: 1,
            7: 1,
        }

    def test_the_year_defaults_to_the_anchor_year(self, me):
        body = me.client.get(_URL, params={"period": "year", "date": "2025-12-31"}).json()

        assert body["total_distance"] == 4000.0

    def test_the_lifetime_summary_counts_every_year(self, me):
        body = me.client.get(_URL, params={"period": "lifetime"}).json()

        assert (body["activity_count"], body["total_distance"]) == (3, 7000.0)
        assert {y["year_number"]: y["activity_count"] for y in body["breakdown"]} == {2026: 2, 2025: 1}


class TestRefusals:
    @pytest.mark.parametrize(
        "params",
        [
            {"period": "decade"},
            {"type": "unicycle"},
            {"date": "not-a-date"},
            {"period": "year", "year": 1899},
            {"period": "year", "year": 10000},
            {"date": "9999-12-31"},
        ],
    )
    def test_a_query_the_route_does_not_accept_is_422(self, me, params):
        assert me.client.get(_URL, params=params).status_code == 422

    def test_a_year_nobody_can_be_living_in_yet_is_400(self, me):
        year = datetime.now(UTC).year + 2

        assert me.client.get(_URL, params={"period": "year", "year": year}).status_code == 400

    def test_the_current_year_is_accepted(self, me):
        assert me.client.get(_URL, params={"period": "year", "year": datetime.now(UTC).year}).status_code == 200
