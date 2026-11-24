"""The water schemas' own rules."""

import pytest
from pydantic import ValidationError

import modules.health.health_water.schema as health_water_schema


class TestAmount:
    @pytest.mark.parametrize("amount", [0, 500.5, health_water_schema.MAX_WATER_ML])
    def test_an_amount_from_zero_up_to_the_daily_cap_is_accepted(self, amount):
        assert health_water_schema.HealthWaterCreate(amount_ml=amount).amount_ml == amount

    @pytest.mark.parametrize("amount", [-1, health_water_schema.MAX_WATER_ML + 1, "500", True])
    def test_anything_else_is_refused(self, amount):
        with pytest.raises(ValidationError):
            health_water_schema.HealthWaterCreate(amount_ml=amount)

    def test_an_amount_is_required_to_create_but_not_to_edit(self):
        with pytest.raises(ValidationError):
            health_water_schema.HealthWaterCreate()
        assert health_water_schema.HealthWaterUpdate(date="2025-03-01").amount_ml is None


class TestWrites:
    def test_a_client_write_refuses_fields_the_server_owns(self):
        for field, value in (("source", "garmin"), ("id", "x"), ("user_id", "x"), ("version", 1)):
            with pytest.raises(ValidationError):
                health_water_schema.HealthWaterCreate(amount_ml=1, **{field: value})

    def test_an_edit_cannot_clear_the_amount_or_the_date(self):
        for field in ("amount_ml", "date"):
            with pytest.raises(ValidationError):
                health_water_schema.HealthWaterUpdate(**{field: None})

    def test_a_date_outside_the_recordable_range_is_refused(self):
        for day in ("1899-12-31", "not-a-date"):
            with pytest.raises(ValidationError):
                health_water_schema.HealthWaterCreate(amount_ml=1, date=day)

    def test_an_import_without_a_source_is_manual_and_a_source_must_be_known(self):
        assert health_water_schema.HealthWaterImport(amount_ml=1).source == "manual"
        with pytest.raises(ValidationError):
            health_water_schema.HealthWaterImport(amount_ml=1, source="invalid")
