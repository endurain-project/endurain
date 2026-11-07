"""A manual health record may not be dated after the athlete's local today, whichever record it is."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

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
import modules.health.record_service as record_service

_TODAY = date(2024, 1, 15)
_TOMORROW = _TODAY + timedelta(days=1)


@pytest.fixture(autouse=True)
def _athlete_clock():
    with (
        patch("modules.users.users.integration_service.local_today", return_value=_TODAY),
        patch("modules.users.users.integration_service.resolve_timezone", return_value="Pacific/Auckland"),
    ):
        yield


class TestRequireNotFuture:
    def test_no_date_is_accepted(self):
        record_service.require_not_future(1, None, MagicMock(), what="A weight")

    def test_today_is_accepted(self):
        record_service.require_not_future(1, _TODAY, MagicMock(), what="A weight")

    def test_tomorrow_is_refused_with_the_record_named(self):
        with pytest.raises(core_exceptions.InvalidInputError, match="A weight cannot be dated in the future"):
            record_service.require_not_future(1, _TOMORROW, MagicMock(), what="A weight")

    def test_an_instant_counts_as_the_day_it_falls_on_in_the_athletes_zone(self):
        # 2024-01-15 23:00 UTC is already the 16th in Auckland.
        with pytest.raises(core_exceptions.InvalidInputError):
            record_service.require_not_future(1, datetime(2024, 1, 15, 23, tzinfo=UTC), MagicMock(), what="A fast")
        record_service.require_not_future(1, datetime(2024, 1, 15, 8, tzinfo=UTC), MagicMock(), what="A fast")


class TestEveryRecordRefusesTheFuture:
    def test_steps(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            steps_service.create_health_steps(1, steps_schema.HealthStepsCreate(date=_TOMORROW, steps=5), MagicMock())
        with pytest.raises(core_exceptions.InvalidInputError):
            steps_service.edit_health_steps(
                1, 1, steps_schema.HealthStepsUpdate(date=_TOMORROW), MagicMock(), if_match="*"
            )

    def test_water(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            water_service.create_health_water(
                1, water_schema.HealthWaterCreate(date=_TOMORROW, amount_ml=250), MagicMock()
            )
        with pytest.raises(core_exceptions.InvalidInputError):
            water_service.edit_health_water(
                1, 1, water_schema.HealthWaterUpdate(date=_TOMORROW), MagicMock(), if_match="*"
            )

    def test_sleep(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            sleep_service.create_health_sleep(1, sleep_schema.HealthSleepCreate(date=_TOMORROW), MagicMock())
        with pytest.raises(core_exceptions.InvalidInputError):
            sleep_service.edit_health_sleep(
                1, 1, sleep_schema.HealthSleepUpdate(date=_TOMORROW), MagicMock(), if_match="*"
            )

    def test_poop(self):
        when = datetime.now(UTC) + timedelta(hours=20)
        with patch("modules.users.users.integration_service.local_today", return_value=when.date() - timedelta(days=2)):
            with pytest.raises(core_exceptions.InvalidInputError):
                poop_service.create_health_poop(1, poop_schema.HealthPoopCreate(date_time=when), MagicMock())
            with pytest.raises(core_exceptions.InvalidInputError):
                poop_service.edit_health_poop(
                    1, 1, poop_schema.HealthPoopUpdate(date_time=when), MagicMock(), if_match="*"
                )

    def test_fasting(self):
        when = datetime.now(UTC) + timedelta(hours=20)
        with patch("modules.users.users.integration_service.local_today", return_value=when.date() - timedelta(days=2)):
            with pytest.raises(core_exceptions.InvalidInputError):
                fasting_service.create_health_fasting(
                    1, fasting_schema.HealthFastingCreate(fast_start_time=when), MagicMock()
                )
            with pytest.raises(core_exceptions.InvalidInputError):
                fasting_service.complete_health_fasting(
                    1, 1, fasting_schema.HealthFastingComplete(fast_end_time=when), MagicMock(), if_match="*"
                )
