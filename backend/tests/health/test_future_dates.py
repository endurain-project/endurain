"""A manual health record may not be dated after the athlete's local today, whichever record it is."""

from datetime import UTC, date, datetime, timedelta

import jasil.runtime as platform_runtime
import pytest

import core.exceptions as core_exceptions
import modules.health.health_fasting.schema as fasting_schema
import modules.health.health_fasting.service as fasting_service
import modules.health.health_poop.schema as poop_schema
import modules.health.health_poop.service as poop_service
import modules.health.health_sleep.schema as sleep_schema
import modules.health.health_sleep.service as sleep_service
import modules.health.health_steps.schema as steps_schema
import modules.health.health_steps.service as steps_service
import modules.health.health_water.schema as water_schema
import modules.health.health_water.service as water_service
import modules.health.health_weight.schema as weight_schema
import modules.health.health_weight.service as weight_service
import modules.health.record_service as record_service
from tests._factories import health as health_factories
from tests._factories.users import make_user

# 08:00 UTC on 15 January is 21:00 that day in Auckland (UTC+13), which makes the 16th the athlete's tomorrow.
_NOW = datetime(2024, 1, 15, 8, tzinfo=UTC)
_TODAY = date(2024, 1, 15)
_TOMORROW = _TODAY + timedelta(days=1)
_LATER = _NOW + timedelta(hours=20)


@pytest.fixture(autouse=True)
def clock():
    platform_clock = platform_runtime.get_active_platform().clock
    platform_clock.moment = _NOW
    return platform_clock


@pytest.fixture
def user(db):
    return make_user(db, timezone="Pacific/Auckland")


class TestRequireNotFuture:
    def test_no_date_is_accepted(self, db, user):
        record_service.require_not_future(user.id, None, db, what="A weight")

    def test_today_is_accepted(self, db, user):
        record_service.require_not_future(user.id, _TODAY, db, what="A weight")

    def test_tomorrow_is_refused_with_the_record_named(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError, match="A weight cannot be dated in the future"):
            record_service.require_not_future(user.id, _TOMORROW, db, what="A weight")

    def test_an_instant_counts_as_the_day_it_falls_on_in_the_athletes_zone(self, db, user):
        # 23:00 UTC on the 15th is already the 16th in Auckland.
        with pytest.raises(core_exceptions.InvalidInputError):
            record_service.require_not_future(user.id, datetime(2024, 1, 15, 23, tzinfo=UTC), db, what="A fast")
        record_service.require_not_future(user.id, datetime(2024, 1, 15, 8, tzinfo=UTC), db, what="A fast")

    def test_the_athletes_today_moves_with_the_platform_clock(self, db, user, clock):
        # 12:00 UTC on the 15th is 01:00 on the 16th in Auckland, so the 16th is today and the 17th is tomorrow.
        clock.moment = datetime(2024, 1, 15, 12, tzinfo=UTC)

        record_service.require_not_future(user.id, _TOMORROW, db, what="A weight")
        with pytest.raises(core_exceptions.InvalidInputError):
            record_service.require_not_future(user.id, _TOMORROW + timedelta(days=1), db, what="A weight")


def _weight(db, user):
    record = health_factories.make_health_weight(db, user.id, date=_TODAY, weight_kg=70.0)
    return (
        lambda: weight_service.create_health_weight(
            user.id, weight_schema.HealthWeightCreate(date=_TOMORROW, weight_kg=70.0), db
        ),
        lambda: weight_service.edit_health_weight(
            user.id, record.id, weight_schema.HealthWeightUpdate(date=_TOMORROW), db, if_match='"1"'
        ),
    )


def _steps(db, user):
    record = health_factories.make_health_steps(db, user.id, date=_TODAY)
    return (
        lambda: steps_service.create_health_steps(user.id, steps_schema.HealthStepsCreate(date=_TOMORROW, steps=5), db),
        lambda: steps_service.edit_health_steps(
            user.id, record.id, steps_schema.HealthStepsUpdate(date=_TOMORROW), db, if_match='"1"'
        ),
    )


def _water(db, user):
    record = health_factories.make_health_water(db, user.id, date=_TODAY)
    return (
        lambda: water_service.create_health_water(
            user.id, water_schema.HealthWaterCreate(date=_TOMORROW, amount_ml=250), db
        ),
        lambda: water_service.edit_health_water(
            user.id, record.id, water_schema.HealthWaterUpdate(date=_TOMORROW), db, if_match='"1"'
        ),
    )


def _sleep(db, user):
    record = health_factories.make_health_sleep(db, user.id, date=_TODAY)
    return (
        lambda: sleep_service.create_health_sleep(user.id, sleep_schema.HealthSleepCreate(date=_TOMORROW), db),
        lambda: sleep_service.edit_health_sleep(
            user.id, record.id, sleep_schema.HealthSleepUpdate(date=_TOMORROW), db, if_match='"1"'
        ),
    )


def _poop(db, user):
    record = health_factories.make_health_poop(db, user.id, date_time=_NOW)
    return (
        lambda: poop_service.create_health_poop(user.id, poop_schema.HealthPoopCreate(date_time=_LATER), db),
        lambda: poop_service.edit_health_poop(
            user.id, record.id, poop_schema.HealthPoopUpdate(date_time=_LATER), db, if_match='"1"'
        ),
    )


def _fasting(db, user):
    record = health_factories.make_health_fasting(db, user.id, fast_start_time=_NOW - timedelta(hours=2))
    return (
        lambda: fasting_service.create_health_fasting(
            user.id, fasting_schema.HealthFastingCreate(fast_start_time=_LATER), db
        ),
        lambda: fasting_service.complete_health_fasting(
            user.id, record.id, fasting_schema.HealthFastingComplete(fast_end_time=_LATER), db, if_match='"1"'
        ),
    )


@pytest.mark.parametrize(
    "arrange",
    [_weight, _steps, _water, _sleep, _poop, _fasting],
    ids=["weight", "steps", "water", "sleep", "poop", "fasting"],
)
class TestEveryRecordRefusesTheFuture:
    def test_a_create_is_refused(self, db, user, arrange):
        create, _ = arrange(db, user)

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            create()

    def test_an_edit_is_refused(self, db, user, arrange):
        _, edit = arrange(db, user)

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            edit()
