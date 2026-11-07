"""Every health record has a ``manual`` source by default, and an old archive's field names are read as today's."""

import importlib

import pytest

import modules.health.health_sleep.schema as sleep_schema
import modules.health.health_targets.schema as targets_schema
import modules.health.health_targets.service as targets_service
import modules.health.health_weight.schema as weight_schema
import modules.health.health_weight.service as weight_service
import modules.health.record_service as health_record_service

_KINDS = ["weight", "steps", "sleep", "water", "poop", "fasting"]
_REQUIRED = {
    "weight": {"weight_kg": 70.0},
    "steps": {"steps": 10},
    "sleep": {},
    "water": {"amount_ml": 10},
    "poop": {"date_time": "2026-01-01T07:00:00Z"},
    "fasting": {"fast_start_time": "2026-01-01T07:00:00Z"},
}


def _schema(kind: str):
    return importlib.import_module(f"modules.health.health_{kind}.schema")


@pytest.mark.parametrize("kind", _KINDS)
def test_every_source_enum_includes_manual(kind):
    assert _schema(kind).Source.MANUAL.value == "manual"


@pytest.mark.parametrize("kind", _KINDS)
def test_a_record_written_by_the_server_without_a_source_is_manual(kind):
    record = getattr(_schema(kind), f"Health{kind.capitalize()}Import")(**_REQUIRED[kind])

    assert record.source == "manual"


@pytest.mark.parametrize("kind", _KINDS)
def test_a_record_read_without_a_source_is_manual(kind):
    read = getattr(_schema(kind), f"Health{kind.capitalize()}Read")
    fields = {"id": 1, "user_id": 1, **_REQUIRED[kind]}
    if kind == "poop":
        fields["date_time"] = "2026-01-01T07:00:00Z"
    if kind == "fasting":
        fields["fast_start_time"] = "2026-01-01T07:00:00Z"

    assert read(**fields).source == "manual"


class TestInCurrentNames:
    def test_old_names_are_read_as_the_current_ones(self):
        row = {"weight": 70.0, "body_fat": 15.0, "bmi": 22.0}
        renamed = {"weight": "weight_kg", "body_fat": "body_fat_percent"}

        assert health_record_service.in_current_names(row, renamed) == {
            "weight_kg": 70.0,
            "body_fat_percent": 15.0,
            "bmi": 22.0,
        }

    def test_current_names_are_left_alone(self):
        assert health_record_service.in_current_names({"weight_kg": 70.0}, {"weight": "weight_kg"}) == {
            "weight_kg": 70.0
        }

    def test_a_null_source_is_dropped_so_the_default_applies(self):
        assert health_record_service.in_current_names({"steps": 1, "source": None}, {}) == {"steps": 1}
        assert health_record_service.in_current_names({"steps": 1, "source": "garmin"}, {}) == {
            "steps": 1,
            "source": "garmin",
        }


def test_the_archive_renames_name_a_field_each_schema_has():
    assert set(weight_service._ARCHIVE_RENAMES.values()) <= set(weight_schema.HealthWeightImport.model_fields)
    assert set(targets_service._ARCHIVE_RENAMES.values()) <= set(targets_schema.HealthTargetsUpdate.model_fields)
    assert {"avg_spo2_percent", "lowest_spo2_percent", "highest_spo2_percent"} <= set(
        sleep_schema.HealthSleepImport.model_fields
    )
