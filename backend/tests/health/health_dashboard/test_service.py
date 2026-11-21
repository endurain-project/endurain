"""The daily dashboard's assembly, on the real database."""

from datetime import UTC, datetime, timedelta

import pytest

import core.timezone as core_timezone
import modules.health.health_dashboard.service as health_dashboard_service
import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_targets.schema as health_targets_schema
from tests._factories.health import (
    make_health_fasting,
    make_health_poop,
    make_health_sleep,
    make_health_steps,
    make_health_water,
    make_health_weight,
)
from tests._factories.users import make_user


def _today():
    return core_timezone.today_in(core_timezone.or_default(None))


def _midday(day):
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)


@pytest.fixture
def user(db):
    return make_user(db, timezone="UTC")


def _stats(db, user, *, include_targets=True):
    return health_dashboard_service.get_daily_stats(user.id, db, include_targets=include_targets)


class TestGetDailyStats:
    def test_a_user_without_data_has_every_metric_empty_and_only_the_empty_targets(self, db, user):
        result = _stats(db, user)

        assert result.model_dump(exclude={"targets"}) == dict.fromkeys(
            ("sleep", "weight", "steps", "fasting", "water", "poop")
        )
        assert result.targets is not None
        assert result.targets.user_id == user.id

    def test_every_metric_is_read_from_the_users_own_records_of_today(self, db, user):
        today = _today()
        make_health_sleep(
            db,
            user.id,
            date=today,
            total_sleep_seconds=28800,
            resting_heart_rate=50,
            hrv_status="BALANCED",
            avg_skin_temp_deviation=0.1,
        )
        make_health_weight(db, user.id, date=today, weight_kg=75.5, bmi=24.5)
        make_health_steps(db, user.id, date=today, steps=8000)
        make_health_water(db, user.id, date=today, amount_ml=1500)
        make_health_poop(db, user.id, date_time=_midday(today))
        make_health_poop(db, user.id, date_time=_midday(today) + timedelta(hours=1))
        fast = make_health_fasting(db, user.id, fast_start_time=_midday(today))

        result = _stats(db, user)

        assert (result.sleep.total_sleep_seconds, result.sleep.resting_heart_rate, result.sleep.hrv_status) == (
            28800,
            50,
            "BALANCED",
        )
        assert result.sleep.avg_skin_temp_deviation == 0.1
        assert (result.weight.weight_kg, result.weight.bmi) == (75.5, 24.5)
        assert result.steps.steps == 8000
        assert (result.fasting.id, result.fasting.status, result.fasting.fast_end_time) == (
            fast.id,
            "in_progress",
            None,
        )
        assert result.water.amount_ml == 1500.0
        assert result.poop.count == 2

    def test_records_of_other_days_are_left_out_except_the_latest_weight(self, db, user):
        today = _today()
        yesterday = today - timedelta(days=1)
        make_health_sleep(db, user.id, date=yesterday)
        make_health_steps(db, user.id, date=yesterday)
        make_health_water(db, user.id, date=yesterday)
        make_health_poop(db, user.id, date_time=_midday(yesterday))
        make_health_weight(db, user.id, date=yesterday, weight_kg=71.0)
        make_health_weight(db, user.id, date=today + timedelta(days=1), weight_kg=99.0)

        result = _stats(db, user)

        assert (result.sleep, result.steps, result.water, result.poop) == (None, None, None, None)
        assert result.weight.weight_kg == 71.0

    def test_another_users_records_are_not_shown(self, db, user):
        other = make_user(db, timezone="UTC")
        make_health_steps(db, other.id, date=_today())
        make_health_weight(db, other.id, date=_today())

        result = _stats(db, user)

        assert (result.steps, result.weight) == (None, None)

    def test_sleep_without_an_hrv_status_is_still_shown(self, db, user):
        make_health_sleep(db, user.id, date=_today(), total_sleep_seconds=27000)

        sleep = _stats(db, user).sleep

        assert (sleep.total_sleep_seconds, sleep.hrv_status) == (27000, None)

    def test_a_finished_fast_is_not_active(self, db, user):
        start = _midday(_today() - timedelta(days=2))
        fast = make_health_fasting(db, user.id, fast_start_time=start)
        health_fasting_crud.end_health_fasting(
            user.id, fast.id, start + timedelta(hours=16), "completed", 57600, None, db, if_match='"1"'
        )

        assert _stats(db, user).fasting is None

    def test_targets_are_left_out_without_the_scope(self, db, user):
        assert _stats(db, user, include_targets=False).targets is None

    def test_the_users_targets_are_included_with_their_values(self, db, user):
        import modules.health.health_targets.crud as health_targets_crud

        health_targets_crud.edit_health_targets(
            health_targets_schema.HealthTargetsUpdate(steps=9000), user.id, db, if_match='"1"'
        )

        assert _stats(db, user).targets.steps == 9000
