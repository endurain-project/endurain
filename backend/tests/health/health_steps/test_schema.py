"""The steps schemas' own rules."""

import pytest
from pydantic import ValidationError

import core.types as core_types
import modules.health.health_steps.schema as health_steps_schema


class TestStepCount:
    @pytest.mark.parametrize("steps", [0, 50000, core_types.INT32_MAX])
    def test_a_count_from_zero_up_to_the_integer_column_maximum_is_accepted(self, steps):
        assert health_steps_schema.HealthStepsCreate(steps=steps).steps == steps

    @pytest.mark.parametrize("steps", [-1, core_types.INT32_MAX + 1, 1.5, "100", True])
    def test_anything_else_is_refused(self, steps):
        with pytest.raises(ValidationError):
            health_steps_schema.HealthStepsCreate(steps=steps)

    def test_a_count_is_required_to_create_but_not_to_edit(self):
        with pytest.raises(ValidationError):
            health_steps_schema.HealthStepsCreate()
        assert health_steps_schema.HealthStepsUpdate(date="2025-03-01").steps is None


class TestWrites:
    def test_a_client_write_refuses_fields_the_server_owns(self):
        for field, value in (("source", "garmin"), ("id", "x"), ("user_id", "x"), ("version", 1)):
            with pytest.raises(ValidationError):
                health_steps_schema.HealthStepsCreate(steps=1, **{field: value})

    def test_an_edit_cannot_clear_the_count_or_the_date(self):
        for field in ("steps", "date"):
            with pytest.raises(ValidationError):
                health_steps_schema.HealthStepsUpdate(**{field: None})

    def test_a_date_outside_the_recordable_range_is_refused(self):
        for day in ("1899-12-31", "not-a-date"):
            with pytest.raises(ValidationError):
                health_steps_schema.HealthStepsCreate(steps=1, date=day)

    def test_an_import_without_a_source_is_manual_and_a_source_must_be_known(self):
        assert health_steps_schema.HealthStepsImport(steps=1).source == "manual"
        with pytest.raises(ValidationError):
            health_steps_schema.HealthStepsImport(steps=1, source="invalid")
