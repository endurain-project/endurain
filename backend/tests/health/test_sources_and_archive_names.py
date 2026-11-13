"""Every health record has a ``manual`` source by default."""

import importlib
import uuid

import pytest

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
    fields = {"id": uuid.uuid4(), "user_id": uuid.uuid4(), "updated_at": "2026-01-01T00:00:00Z", **_REQUIRED[kind]}
    if kind == "poop":
        fields["date_time"] = "2026-01-01T07:00:00Z"
    if kind == "fasting":
        fields["fast_start_time"] = "2026-01-01T07:00:00Z"

    assert read(**fields).source == "manual"
