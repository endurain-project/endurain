"""The columnar samples a file yields: the invariants of every device file, and how the builder cuts them.

Every ``.fit``, ``.gpx`` and ``.tcx`` under ``fixtures/`` and every synthetic case is parsed through the parser
registry as ingestion does, and what its samples hold is pinned in the goldens of ``test_device_files.py``. Here is
what holds for all of them.
"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity_file_import.parser_registry as registry
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
from tests.activities.activity_file_import import synthetic_files
from tests.activities.activity_file_import.assembled import assemble_file, make_recording, session

_FIXTURES = Path(__file__).parent / "fixtures"
_EXTENSIONS = {".fit", ".gpx", ".tcx"}
_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_START = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)


def _fixture_paths() -> list[str]:
    real = sorted(
        path.relative_to(_FIXTURES).as_posix()
        for path in _FIXTURES.rglob("*")
        if path.is_file() and path.suffix.lower() in _EXTENSIONS and "synthetic" not in path.parts
    )
    return [*real, *(f"synthetic/{name}" for name in synthetic_files.CASES)]


def _parse(name: str, tmp_path: Path) -> activity_contracts.ParsedFile:
    if name.startswith("synthetic/"):
        path = tmp_path / Path(name).name
        path.write_bytes(synthetic_files.CASES[name.removeprefix("synthetic/")]())
    else:
        path = _FIXTURES / name
    parser = registry.get_parser(path.suffix)
    assert parser is not None
    return parser(str(path), _USER_ID, None, "Europe/Lisbon", 1.0)


def _assert_consistent(samples: activity_streams_contracts.ParsedSamples) -> None:
    assert samples.offsets_ms == sorted(samples.offsets_ms)
    present = [name for name in activity_streams_constants.SAMPLE_CHANNELS if getattr(samples, name) is not None]
    assert present, "samples with no channel are not stored"
    for name in present:
        assert any(value is not None for value in getattr(samples, name)), name
    # A position is both coordinates or neither.
    if samples.latitude is not None and samples.longitude is not None:
        assert all((lat is None) == (lon is None) for lat, lon in zip(samples.latitude, samples.longitude, strict=True))


@pytest.mark.parametrize("name", _fixture_paths(), ids=lambda name: name)
def test_the_samples_of_every_device_file_are_consistent(name: str, tmp_path: Path) -> None:
    try:
        parsed_file = _parse(name, tmp_path)
    except core_exceptions.DomainError:
        pytest.skip("the file is refused by the parser")
    for parsed in parsed_file.activities:
        assert "streams" not in parsed.components
        samples = parsed.components.get("samples")
        if samples is not None:
            _assert_consistent(samples)
    if parsed_file.parent is not None:
        assert parsed_file.parent.components.get("samples") is None
        assert all(leg.components.get("samples") is not None for leg in parsed_file.activities)


def _rows(count: int, **channels) -> list[dict]:
    return [
        {"time": _START + timedelta(milliseconds=1000 * i + 250), **{k: v[i] for k, v in channels.items()}}
        for i in range(count)
    ]


class TestBuiltSamples:
    def test_offsets_are_milliseconds_from_the_whole_second_start_at_the_samples_own_times(self):
        rec = make_recording(
            session(
                [
                    {"time": _START + timedelta(milliseconds=250), "heart_rate": 100},
                    {"time": _START + timedelta(milliseconds=1999, microseconds=900), "heart_rate": 110},
                    {"time": _START + timedelta(seconds=3), "heart_rate": 120},
                ],
                start_time=_START + timedelta(milliseconds=250),
            )
        )

        (payload,) = assemble_file(rec).activities

        assert payload["activity"].start_time == _START
        assert payload["samples"].offsets_ms == [250, 1999, 3000]

    def test_a_channel_the_session_never_has_is_none_and_a_dropout_is_a_none_element(self):
        rec = make_recording(session(_rows(3, heart_rate=[100, None, 120])))

        (payload,) = assemble_file(rec).activities

        samples = payload["samples"]
        assert samples.heart_rate == [100, None, 120]
        assert samples.power is None
        assert samples.latitude is None
        assert samples.longitude is None

    def test_a_running_session_stores_cadence_as_steps_per_minute(self):
        rec = make_recording(session(_rows(2, cadence=[85, 86.5]), sport="running"))

        (payload,) = assemble_file(rec).activities

        assert payload["samples"].cadence == [170, 173]

    def test_a_cycling_session_stores_cadence_as_recorded(self):
        rec = make_recording(session(_rows(2, cadence=[85, 90]), sport="cycling"))

        (payload,) = assemble_file(rec).activities

        assert payload["samples"].cadence == [85, 90]

    def test_a_sample_with_only_one_coordinate_has_neither(self):
        rec = make_recording(session(_rows(3, lat=[38.0, 38.1, None], lon=[-9.0, None, -9.2])))

        (payload,) = assemble_file(rec).activities

        assert payload["samples"].latitude == [38.0, None, None]
        assert payload["samples"].longitude == [-9.0, None, None]

    def test_a_session_without_samples_has_no_samples(self):
        (payload,) = assemble_file(make_recording(session([]))).activities

        assert payload["samples"] is None


class TestSpeedChannel:
    def test_a_device_speed_is_stored_as_recorded_and_a_sample_without_one_has_none(self):
        rec = make_recording(session(_rows(3, speed=[2.0, None, 4.0])))

        (payload,) = assemble_file(rec).activities

        assert payload["samples"].speed == [2.0, None, 4.0]

    def test_a_speed_derived_from_positions_has_a_zero_placeholder_for_the_first_fix(self):
        rec = make_recording(session(_rows(3, lat=[40.0, 40.0001, 40.0002], lon=[-3.0, -3.0, -3.0])))

        (payload,) = assemble_file(rec).activities

        speed = payload["samples"].speed
        assert speed[0] == 0
        assert speed[1:] == pytest.approx([11.1, 11.1], abs=0.2)

    def test_a_track_without_positions_or_device_speed_has_no_speed_channel(self):
        rec = make_recording(session(_rows(3, heart_rate=[100, 101, 102])))

        (payload,) = assemble_file(rec).activities

        assert payload["samples"].speed is None


class TestElevationChannel:
    def test_the_elevation_is_smoothed_over_time_at_the_samples_that_have_an_altitude(self):
        altitude = [0.0] * 10 + [11.0] * 10
        rec = make_recording(session(_rows(20, altitude=altitude)))

        (payload,) = assemble_file(rec).activities

        elevation = payload["samples"].elevation
        assert len(elevation) == 20
        # The step is averaged over the 10 s around each sample, so the middle of the step is no longer 0 or 11.
        assert 0 < elevation[10] < 11
        assert elevation[0] == pytest.approx(0.0, abs=1.5)

    def test_a_sample_without_an_altitude_has_no_elevation(self):
        rec = make_recording(session(_rows(3, altitude=[100.0, None, 102.0])))

        (payload,) = assemble_file(rec).activities

        assert payload["samples"].elevation[1] is None


class TestStartPoint:
    def test_the_start_point_is_the_first_sample_with_both_coordinates(self):
        rec = make_recording(session(_rows(3, lat=[None, 38.1, 38.2], lon=[None, -9.1, -9.2])))

        (payload,) = assemble_file(rec).activities

        assert (payload["activity"].start_latitude, payload["activity"].start_longitude) == (38.1, -9.1)

    def test_an_indoor_session_has_no_start_point(self):
        (payload,) = assemble_file(make_recording(session(_rows(3, heart_rate=[100, 101, 102])))).activities

        assert payload["activity"].start_latitude is None
        assert payload["activity"].start_longitude is None

    def test_a_multisport_parent_takes_the_start_point_of_its_first_leg_that_has_one(self):
        indoor = session(_rows(2, heart_rate=[100, 101]), sport="cycling", start_time=_START, summary=_summary(60))
        run = session(
            [{"time": _START + timedelta(seconds=100 + i), "lat": 38.5 + i, "lon": -9.5 + i} for i in range(2)],
            sport="running",
            start_time=_START + timedelta(seconds=100),
            summary=_summary(60),
        )
        ride = session(
            [{"time": _START + timedelta(seconds=300 + i), "lat": 40.0 + i, "lon": -8.0 + i} for i in range(2)],
            sport="cycling",
            start_time=_START + timedelta(seconds=300),
            summary=_summary(60),
        )

        assembled = assemble_file(make_recording(indoor, run, ride, multisport=True))

        assert assembled.parent is not None
        assert (assembled.parent["activity"].start_latitude, assembled.parent["activity"].start_longitude) == (
            38.5,
            -9.5,
        )
        assert assembled.parent["samples"] is None


def _summary(elapsed: int):
    import modules.activities.activity_file_import.recording as recording

    return recording.DeviceSummary(total_elapsed_time=elapsed, total_timer_time=elapsed)
