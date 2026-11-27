"""The columnar samples a file yields agree with the waypoint streams stored for the same file.

Every ``.fit``, ``.gpx`` and ``.tcx`` under ``fixtures/`` and every synthetic case is parsed through the parser
registry as ingestion does. The comparison rule: an old waypoint's ``time`` is its sample's instant cut to whole
seconds, so a sample at ``start_time + offsets_ms[i]`` is stamped the same way, and for each stream the old waypoints
equal, in order, the samples whose channel is not ``None`` (a sub-second file has several samples under one stamp, and
each one has its own waypoint). Pace has no channel: its waypoints equal ``1 / speed`` for every speed above zero.
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
_STAMP = "%Y-%m-%dT%H:%M:%S"

#: stream type -> (samples channel, waypoint key)
_SCALAR_STREAMS = {
    activity_streams_constants.STREAM_TYPE_HR: ("heart_rate", "hr"),
    activity_streams_constants.STREAM_TYPE_POWER: ("power", "power"),
    activity_streams_constants.STREAM_TYPE_CADENCE: ("cadence", "cad"),
    activity_streams_constants.STREAM_TYPE_ELEVATION: ("elevation", "ele"),
    activity_streams_constants.STREAM_TYPE_SPEED: ("speed", "vel"),
    activity_streams_constants.STREAM_TYPE_TEMPERATURE: ("temperature", "temp"),
}


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


def _stamps(parsed: activity_contracts.ParsedActivity) -> list[str]:
    samples = parsed.components["samples"]
    assert isinstance(samples, activity_streams_contracts.ParsedSamples)
    return [
        (parsed.activity.start_time + timedelta(milliseconds=offset)).strftime(_STAMP) for offset in samples.offsets_ms
    ]


def _present(stamps: list[str], channel: list[float | None] | None) -> list[tuple[str, float]]:
    if channel is None:
        return []
    return [(stamp, value) for stamp, value in zip(stamps, channel, strict=True) if value is not None]


def _assert_agrees(parsed: activity_contracts.ParsedActivity) -> None:
    samples = parsed.components["samples"]
    streams = {stream.stream_type: stream for stream in parsed.components["streams"]}
    stamps = _stamps(parsed)
    for stream_type, (channel, key) in _SCALAR_STREAMS.items():
        stream = streams.get(stream_type)
        old = [] if stream is None else [(w["time"], w[key]) for w in stream.stream_waypoints]
        assert _present(stamps, getattr(samples, channel)) == old, channel
        assert (getattr(samples, channel) is None) == (stream is None), channel

    map_stream = streams.get(activity_streams_constants.STREAM_TYPE_MAP)
    old_map = [] if map_stream is None else [(w["time"], (w["lat"], w["lon"])) for w in map_stream.stream_waypoints]
    latitude = samples.latitude or [None] * len(stamps)
    longitude = samples.longitude or [None] * len(stamps)
    new_map = [
        (stamp, (lat, lon))
        for stamp, lat, lon in zip(stamps, latitude, longitude, strict=True)
        if lat is not None and lon is not None
    ]
    assert new_map == old_map
    assert all((lat is None) == (lon is None) for lat, lon in zip(latitude, longitude, strict=True))
    assert (samples.latitude is None) == (map_stream is None)

    pace_stream = streams.get(activity_streams_constants.STREAM_TYPE_PACE)
    old_pace = [] if pace_stream is None else [(w["time"], w["pace"]) for w in pace_stream.stream_waypoints]
    assert [(stamp, 1 / value) for stamp, value in _present(stamps, samples.speed) if value > 0] == old_pace


@pytest.mark.parametrize("name", _fixture_paths(), ids=lambda name: name)
def test_samples_agree_with_the_streams_of_every_device_file(name: str, tmp_path: Path) -> None:
    try:
        parsed_file = _parse(name, tmp_path)
    except core_exceptions.DomainError:
        pytest.skip("the file is refused by the parser")
    for parsed in parsed_file.activities:
        if parsed.components.get("samples") is None:
            assert not parsed.components["streams"], "a session with streams has samples"
            continue
        _assert_agrees(parsed)
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
