"""Golden snapshots of what the file parsers produce for real device files and synthetic edge cases.

Every ``.fit``, ``.gpx`` and ``.tcx`` under ``fixtures/`` is parsed through the parser registry exactly as ingestion
does, and a summary of the result (activity fields, per-stream statistics and digest, laps, sets, workout steps, file
components, or the domain error raised) is compared with the ``<file>.golden.json`` beside it. The edge cases no real
file exists for are built in code by ``synthetic_files.py``, written to a temporary file and snapshotted the same
way; their goldens live under ``fixtures/synthetic/<format>/``. A parser change shows up as a golden diff to review.
Regenerate with::

    uv run pytest tests/activities/activity_file_import/test_device_files.py --update-golden
"""

import dataclasses
import hashlib
import json
import uuid
from datetime import date, datetime
from pathlib import Path
from statistics import fmean

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.parser_registry as registry
from tests.activities.activity_file_import import synthetic_files

_FIXTURES = Path(__file__).parent / "fixtures"
_EXTENSIONS = {".fit", ".gpx", ".tcx"}
_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
# Fixed ingestion defaults: the default timezone and the lap distance in km.
_TIMEZONE = "Europe/Lisbon"
_LAP_DISTANCE_KM = 1.0
_FLOAT_DIGITS = 6


_SYNTHETIC = "synthetic"


def _fixture_names() -> list[str]:
    """Return the real fixture files and the synthetic cases as paths relative to ``fixtures/``."""
    real = sorted(
        path.relative_to(_FIXTURES).as_posix()
        for path in _FIXTURES.rglob("*")
        if path.is_file() and path.suffix.lower() in _EXTENSIONS
    )
    return [*real, *(f"{_SYNTHETIC}/{name}" for name in synthetic_files.CASES)]


def _round_floats(value: object) -> object:
    """Round every float in a JSON-like structure so platform float noise does not churn goldens."""
    if isinstance(value, float):
        return round(value, _FLOAT_DIGITS)
    if isinstance(value, dict):
        return {key: _round_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_floats(item) for item in value]
    return value


def _to_json(value: object) -> object:
    """Convert pydantic models, dataclasses, datetimes and containers to plain JSON values."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "model_dump"):
        return _to_json(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _to_json({f.name: getattr(value, f.name) for f in dataclasses.fields(value)})
    if isinstance(value, dict):
        return {str(key): _to_json(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_json(item) for item in value]
    raise TypeError(f"cannot serialise {type(value).__name__}")


def _field_stats(waypoints: list[dict]) -> dict[str, dict[str, float]]:
    """Return min, max and mean of every numeric non-time key across the waypoints."""
    keys = sorted({key for waypoint in waypoints for key in waypoint if key != "time"})
    stats = {}
    for key in keys:
        values = [
            waypoint[key]
            for waypoint in waypoints
            if isinstance(waypoint.get(key), int | float) and not isinstance(waypoint.get(key), bool)
        ]
        if values:
            stats[key] = {"min": min(values), "max": max(values), "mean": fmean(values)}
    return stats


def _stream_snapshot(stream) -> dict[str, object]:
    waypoints = [dict(waypoint) for waypoint in stream.stream_waypoints]
    digest = hashlib.sha256(json.dumps(waypoints, sort_keys=True, separators=(",", ":"), default=str).encode())
    return {
        "stream_type": stream.stream_type,
        "count": len(waypoints),
        "first": _to_json(waypoints[0]) if waypoints else None,
        "last": _to_json(waypoints[-1]) if waypoints else None,
        "fields": _field_stats(waypoints),
        "sha256": digest.hexdigest(),
    }


def _activity_snapshot(parsed) -> dict[str, object]:
    components = parsed.components
    streams = sorted(components.get("streams") or [], key=lambda stream: stream.stream_type)
    return {
        "activity": parsed.activity.model_dump(mode="json", exclude={"user_id"}),
        "streams": [_stream_snapshot(stream) for stream in streams],
        "laps": _to_json(components.get("laps")),
        "sets": _to_json(components.get("sets")),
        "workout_steps": _to_json(components.get("workout_steps")),
    }


def _snapshot(path: Path) -> dict[str, object]:
    parser = registry.get_parser(path.suffix)
    assert parser is not None
    try:
        parsed_file = parser(str(path), _USER_ID, None, _TIMEZONE, _LAP_DISTANCE_KM)
    except core_exceptions.DomainError as err:
        return {"error": type(err).__name__, "message": str(err)}
    snapshot = {
        "activities": [_activity_snapshot(parsed) for parsed in parsed_file.activities],
        "file_components": _to_json(parsed_file.components),
    }
    return _round_floats(snapshot)


def _golden_text(snapshot: dict[str, object]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("name", _fixture_names(), ids=lambda name: name)
def test_device_file_matches_golden(name: str, request: pytest.FixtureRequest, tmp_path: Path) -> None:
    """A device file or synthetic case parses to the recorded golden snapshot."""
    golden = _FIXTURES / (name + ".golden.json")
    synthetic_name = name.removeprefix(f"{_SYNTHETIC}/")
    if synthetic_name != name:
        path = tmp_path / Path(synthetic_name).name
        path.write_bytes(synthetic_files.CASES[synthetic_name]())
    else:
        path = _FIXTURES / name
    snapshot = _snapshot(path)
    if request.config.getoption("--update-golden"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(_golden_text(snapshot), encoding="utf-8")
        return
    if not golden.exists():
        pytest.fail(f"missing golden file {golden.name}; run with --update-golden to create it")
    assert snapshot == json.loads(golden.read_text(encoding="utf-8"))
