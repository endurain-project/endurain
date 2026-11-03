"""Every date a client writes on a health record is a real one; a stored row is read back as it is."""

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

import modules.health.health_fasting.schema as fasting_schema
import modules.health.health_poop.schema as poop_schema
import modules.health.health_sleep.schema as sleep_schema
import modules.health.health_steps.schema as steps_schema
import modules.health.health_water.schema as water_schema
import modules.health.health_weight.schema as weight_schema

_NOW = datetime.now(UTC)
_TODAY = _NOW.date()

# name -> (schema, required values, the field under test)
_DATES = {
    "water": (water_schema.HealthWaterCreate, {"amount_ml": 250.0}, "date"),
    "water update": (water_schema.HealthWaterUpdate, {}, "date"),
    "steps": (steps_schema.HealthStepsCreate, {"steps": 1000}, "date"),
    "steps update": (steps_schema.HealthStepsUpdate, {}, "date"),
    "weight": (weight_schema.HealthWeightCreate, {"weight": 70.0}, "date"),
    "weight update": (weight_schema.HealthWeightUpdate, {}, "date"),
    "sleep": (sleep_schema.HealthSleepCreate, {}, "date"),
    "sleep update": (sleep_schema.HealthSleepUpdate, {}, "date"),
}
_DATETIMES = {
    "poop": (poop_schema.HealthPoopCreate, {}, "date_time"),
    "poop update": (poop_schema.HealthPoopUpdate, {}, "date_time"),
    "fasting start": (fasting_schema.HealthFastingCreate, {}, "fast_start_time"),
    "fasting end": (fasting_schema.HealthFastingCreate, {"fast_start_time": _NOW}, "fast_end_time"),
    "fasting update start": (fasting_schema.HealthFastingUpdate, {}, "fast_start_time"),
    "fasting update end": (fasting_schema.HealthFastingUpdate, {}, "fast_end_time"),
    "sleep start gmt": (sleep_schema.HealthSleepCreate, {}, "sleep_start_time_gmt"),
    "sleep end gmt": (sleep_schema.HealthSleepCreate, {}, "sleep_end_time_gmt"),
    "sleep start local": (sleep_schema.HealthSleepCreate, {}, "sleep_start_time_local"),
    "sleep end local": (sleep_schema.HealthSleepCreate, {}, "sleep_end_time_local"),
}


@pytest.mark.parametrize("kind", list(_DATES))
class TestRecordDate:
    def test_before_1900_is_rejected(self, kind):
        schema, values, field = _DATES[kind]

        with pytest.raises(ValidationError):
            schema(**values, **{field: date(1899, 12, 31)})

    def test_today_is_accepted(self, kind):
        schema, values, field = _DATES[kind]

        assert getattr(schema(**values, **{field: _TODAY}), field) == _TODAY

    def test_two_days_ahead_is_rejected(self, kind):
        schema, values, field = _DATES[kind]

        with pytest.raises(ValidationError):
            schema(**values, **{field: _TODAY + timedelta(days=2)})


@pytest.mark.parametrize("kind", list(_DATETIMES))
class TestRecordDateTime:
    def test_before_1900_is_rejected(self, kind):
        schema, values, field = _DATETIMES[kind]

        with pytest.raises(ValidationError):
            schema(**values, **{field: datetime(1899, 12, 31, tzinfo=UTC)})

    def test_now_is_accepted(self, kind):
        schema, values, field = _DATETIMES[kind]

        assert getattr(schema(**values, **{field: _NOW}), field) == _NOW

    def test_two_days_ahead_is_rejected(self, kind):
        schema, values, field = _DATETIMES[kind]

        with pytest.raises(ValidationError):
            schema(**values, **{field: _NOW + timedelta(days=2)})


class TestSleepStages:
    @pytest.mark.parametrize("field", ["start_time_gmt", "end_time_gmt"])
    def test_a_stage_time_outside_the_range_is_rejected(self, field):
        for bad in (datetime(1899, 1, 1, tzinfo=UTC), _NOW + timedelta(days=2)):
            with pytest.raises(ValidationError):
                sleep_schema.HealthSleepCreate(sleep_stages=[{"stage_type": 1, field: bad}])

    def test_stages_inside_the_range_are_accepted(self):
        record = sleep_schema.HealthSleepCreate(
            sleep_stages=[{"stage_type": 1, "start_time_gmt": _NOW - timedelta(hours=1), "end_time_gmt": _NOW}]
        )

        assert record.sleep_stages is not None
        assert len(record.sleep_stages) == 1


class TestStoredRowsStayReadable:
    """A row stored before the bound existed is still read, so a list does not fail on it."""

    def test_a_far_future_date_is_read(self):
        read = water_schema.HealthWaterRead(id=1, user_id=1, date=date(9999, 12, 31), amount_ml=1.0)

        assert read.date == date(9999, 12, 31)

    def test_a_far_future_time_is_read(self):
        read = poop_schema.HealthPoopRead(id=1, user_id=1, date_time=datetime(9999, 1, 1, tzinfo=UTC))

        assert read.date_time.year == 9999

    def test_a_far_future_sleep_is_read(self):
        read = sleep_schema.HealthSleepRead(
            id=1,
            user_id=1,
            date=date(9999, 1, 1),
            sleep_stages=[{"stage_type": 1, "start_time_gmt": datetime(9999, 1, 1, tzinfo=UTC)}],
        )

        assert read.date == date(9999, 1, 1)
