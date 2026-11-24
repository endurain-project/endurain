"""The rules the weight schemas enforce on what a client sends."""

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

import core.types as core_types
import modules.health.health_weight.schema as health_weight_schema

_BOUNDED_FIELDS = [
    ("weight_kg", 500),
    ("bmi", health_weight_schema.MAX_BMI),
    ("body_fat_percent", 100),
    ("body_water_percent", 100),
    ("bone_mass_kg", 500),
    ("muscle_mass_kg", 500),
    ("visceral_fat", 100),
    ("physique_rating", core_types.INT32_MAX),
    ("metabolic_age", 120),
]
_SERVER_OWNED = ["id", "user_id", "version", "updated_at", "source"]


def _create(**fields: object) -> health_weight_schema.HealthWeightCreate:
    return health_weight_schema.HealthWeightCreate(**{"weight_kg": 70.0, **fields})


def _tomorrow() -> date:
    return datetime.now(UTC).date() + timedelta(days=1)


class TestFieldBounds:
    @pytest.mark.parametrize(("field", "upper"), _BOUNDED_FIELDS)
    def test_a_value_between_zero_and_its_upper_bound_is_accepted(self, field, upper):
        for value in (0, upper):
            record = _create(**{field: value})

            assert getattr(record, field) == value

    @pytest.mark.parametrize(("field", "upper"), _BOUNDED_FIELDS)
    def test_a_negative_value_is_refused(self, field, upper):
        with pytest.raises(ValidationError):
            _create(**{field: -1})

    @pytest.mark.parametrize(("field", "upper"), _BOUNDED_FIELDS)
    def test_a_value_above_its_upper_bound_is_refused(self, field, upper):
        with pytest.raises(ValidationError):
            _create(**{field: upper + 1})

    @pytest.mark.parametrize("field", ["physique_rating", "metabolic_age"])
    def test_a_score_that_is_not_a_whole_number_is_refused(self, field):
        with pytest.raises(ValidationError):
            _create(**{field: 1.5})

    def test_a_number_sent_as_a_string_is_refused(self):
        with pytest.raises(ValidationError):
            health_weight_schema.HealthWeightCreate(weight_kg="70.5")


class TestCreate:
    def test_a_weight_is_required(self):
        with pytest.raises(ValidationError):
            health_weight_schema.HealthWeightCreate()

    def test_the_date_is_optional(self):
        assert health_weight_schema.HealthWeightCreate(weight_kg=70.0).date is None

    @pytest.mark.parametrize("field", _SERVER_OWNED)
    def test_a_field_the_server_owns_is_refused(self, field):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            _create(**{field: 1})


class TestDateBounds:
    @pytest.mark.parametrize(
        "schema", [health_weight_schema.HealthWeightCreate, health_weight_schema.HealthWeightUpdate]
    )
    def test_a_date_before_1900_is_refused(self, schema):
        with pytest.raises(ValidationError, match="Date must be between"):
            schema(weight_kg=70.0, date=date(1899, 12, 31))

    @pytest.mark.parametrize(
        "schema", [health_weight_schema.HealthWeightCreate, health_weight_schema.HealthWeightUpdate]
    )
    def test_a_date_beyond_tomorrow_is_refused(self, schema):
        with pytest.raises(ValidationError, match="Date must be between"):
            schema(weight_kg=70.0, date=_tomorrow() + timedelta(days=1))

    def test_a_date_up_to_tomorrow_is_accepted(self):
        assert health_weight_schema.HealthWeightCreate(weight_kg=70.0, date=_tomorrow()).date == _tomorrow()

    def test_a_stored_row_read_back_is_not_held_to_the_bounds(self):
        record = health_weight_schema.HealthWeightBase(date=date(1800, 1, 1))

        assert record.date == date(1800, 1, 1)


class TestUpdate:
    def test_an_update_may_carry_any_subset_of_fields(self):
        update = health_weight_schema.HealthWeightUpdate(body_fat_percent=18.5)

        assert update.model_fields_set == {"body_fat_percent"}

    @pytest.mark.parametrize("field", ["date", "weight_kg"])
    def test_a_required_field_cannot_be_cleared(self, field):
        with pytest.raises(ValidationError, match=f"{field} cannot be null"):
            health_weight_schema.HealthWeightUpdate(**{field: None})

    def test_an_optional_field_can_be_cleared(self):
        update = health_weight_schema.HealthWeightUpdate(body_fat_percent=None)

        assert update.body_fat_percent is None
        assert "body_fat_percent" in update.model_fields_set

    @pytest.mark.parametrize("field", _SERVER_OWNED)
    def test_a_field_the_server_owns_is_refused(self, field):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            health_weight_schema.HealthWeightUpdate(**{field: 1})


class TestServerWrites:
    def test_a_provider_import_carries_its_source(self):
        record = health_weight_schema.HealthWeightImport(weight_kg=70.0, source="garmin")

        assert record.source == health_weight_schema.Source.GARMIN.value

    def test_an_import_without_a_source_is_manual(self):
        assert health_weight_schema.HealthWeightImport(weight_kg=70.0).source == "manual"

    def test_a_source_that_is_not_known_is_refused(self):
        with pytest.raises(ValidationError):
            health_weight_schema.HealthWeightImport(weight_kg=70.0, source="fitbit")

    def test_an_import_update_cannot_clear_the_source(self):
        with pytest.raises(ValidationError, match="source cannot be null"):
            health_weight_schema.HealthWeightImportUpdate(source=None)
