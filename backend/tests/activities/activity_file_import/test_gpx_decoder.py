"""Tests for the GPX decoder: what a file decodes to, and which files it refuses."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.gpx_decoder as gpx_decoder
import modules.activities.activity_file_import.recording as activity_file_import_recording
from tests.activities.activity_file_import import synthetic_files

_FIXTURES = Path(__file__).parent / "fixtures"
_START = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)

#: Real exports with a track, by path under ``fixtures/``: sport, name and creator the file gives.
_REAL = {
    "open_water_swim/activity_19967637462.gpx": (
        "open_water_swimming",
        "Balearic Islands Open Water Swimming",
        "Garmin Connect",
    ),
    "outdoor_ride/activity_15234112254.gpx": ("cycling", "Minifondo Douro 2024", "Garmin Connect"),
    "outdoor_ride/activity_15234112254_from_strava.gpx": ("cycling", "Minifondo Douro 2024", "StravaGPX"),
    "outdoor_run/activity_24273515840.gpx": ("running", "Porto - Base", "Garmin Connect"),
}

#: Indoor exports whose track holds no trackpoints.
_EMPTY = [
    "treadmill_run/activity_24280055123.gpx",
    "indoor_ride/activity_24948315262.gpx",
    "pool_swim/activity_25132672571.gpx",
    "strength/activity_24939814804.gpx",
    "hiit/activity_15224321444.gpx",
]


def _decode_bytes(tmp_path: Path, content: bytes) -> activity_file_import_recording.Recording:
    """Write ``content`` to a file and decode it."""
    path = tmp_path / "activity.gpx"
    path.write_bytes(content)
    return gpx_decoder.decode_gpx(str(path))


def _decode_case(tmp_path: Path, name: str) -> activity_file_import_recording.Recording:
    """Decode the synthetic case ``gpx/<name>.gpx``."""
    return _decode_bytes(tmp_path, synthetic_files.CASES[f"gpx/{name}.gpx"]())


def _only_session(recording: activity_file_import_recording.Recording) -> activity_file_import_recording.Session:
    assert len(recording.sessions) == 1
    return recording.sessions[0]


def test_real_fixtures_cover_every_gpx() -> None:
    found = {p.relative_to(_FIXTURES).as_posix() for p in _FIXTURES.rglob("*.gpx") if "synthetic" not in p.parts}
    assert found == set(_REAL) | set(_EMPTY)


@pytest.mark.parametrize("name", sorted(_REAL))
def test_real_fixture_decodes(name: str) -> None:
    path = _FIXTURES / name
    sport, title, creator = _REAL[name]

    recording = gpx_decoder.decode_gpx(str(path))

    session = _only_session(recording)
    assert recording.format == "gpx"
    assert len(session.samples) == len(re.findall(r"<trkpt\b", path.read_text(encoding="utf-8")))
    assert session.sport == sport
    assert recording.name == title
    assert recording.creator == creator
    assert session.start_time == session.samples.time[0]
    assert all(time.tzinfo is not None and time.utcoffset() == timedelta(0) for time in session.samples.time)
    assert list(session.samples.time) == sorted(session.samples.time)
    assert session.laps == ()
    assert all(lat is not None for lat in session.samples.lat)


@pytest.mark.parametrize("name", _EMPTY)
def test_indoor_export_without_trackpoints_is_refused(name: str) -> None:
    with pytest.raises(core_exceptions.InvalidInputError, match="no trackpoints with valid time data"):
        gpx_decoder.decode_gpx(str(_FIXTURES / name))


def test_garmin_and_strava_outdoor_ride_agree() -> None:
    garmin = _only_session(gpx_decoder.decode_gpx(str(_FIXTURES / "outdoor_ride/activity_15234112254.gpx"))).samples
    strava = _only_session(
        gpx_decoder.decode_gpx(str(_FIXTURES / "outdoor_ride/activity_15234112254_from_strava.gpx"))
    ).samples

    assert len(garmin) == len(strava) == 7579
    assert garmin.time == strava.time
    assert garmin.lat == pytest.approx(strava.lat, abs=1e-4)
    assert garmin.lon == pytest.approx(strava.lon, abs=1e-4)
    assert any(value is not None for value in garmin.heart_rate)
    assert any(value is not None for value in garmin.temperature)


def test_multi_track_is_one_session_with_a_pause(tmp_path: Path) -> None:
    recording = _decode_case(tmp_path, "multi_track")

    session = _only_session(recording)
    assert len(session.samples) == 120
    assert recording.name == "Morning Run"
    assert session.sport == "running"
    assert session.summary.calories == 350
    assert len(session.pauses) == 1
    assert session.pauses[0].start == _START + timedelta(seconds=59)
    assert session.pauses[0].end == _START + timedelta(hours=2)


def test_two_segments_pause(tmp_path: Path) -> None:
    session = _only_session(_decode_case(tmp_path, "two_segments_pause"))

    assert len(session.samples) == 400
    assert len(session.pauses) == 1
    assert (session.pauses[0].end - session.pauses[0].start).total_seconds() == pytest.approx(300, abs=2)


def test_contiguous_segments_have_no_pause(tmp_path: Path) -> None:
    content = (
        b'<gpx creator="t"><trk><trkseg><trkpt lat="1" lon="1"><time>2026-06-20T08:00:00Z</time></trkpt>'
        b'<trkpt lat="1" lon="1"><time>2026-06-20T08:00:05Z</time></trkpt></trkseg>'
        b'<trkseg><trkpt lat="1" lon="1"><time>2026-06-20T08:00:05Z</time></trkpt>'
        b'<trkpt lat="1" lon="1"><time>2026-06-20T08:00:09Z</time></trkpt></trkseg></trk></gpx>'
    )

    session = _only_session(_decode_bytes(tmp_path, content))

    assert len(session.samples) == 4
    assert session.pauses == ()


def test_phone_app_keeps_subsecond_times_and_speed(tmp_path: Path) -> None:
    recording = _decode_case(tmp_path, "phone_app_subsecond")

    samples = _only_session(recording).samples
    assert len(samples) == 90
    assert samples.time[0] == _START + timedelta(milliseconds=250)
    assert samples.time[1] - samples.time[0] == timedelta(seconds=1)
    assert set(samples.speed) == {1.4}
    assert all(value is None for value in samples.heart_rate)
    assert recording.creator == "Phone Tracker 1.0"
    assert recording.name is None


def test_power_extension(tmp_path: Path) -> None:
    session = _only_session(_decode_case(tmp_path, "power_extension"))

    assert session.sport == "cycling"
    assert session.samples.power == tuple(200 + i % 50 for i in range(120))
    assert session.samples.heart_rate == tuple(140 + i % 15 for i in range(120))


def test_strava_style_ride(tmp_path: Path) -> None:
    recording = _decode_case(tmp_path, "strava_style_ride")

    samples = _only_session(recording).samples
    assert recording.creator == "StravaGPX"
    assert recording.name == "Lunch Ride"
    assert samples.power == tuple(180 + i % 40 for i in range(120))
    assert samples.cadence == tuple(float(85 + i % 5) for i in range(120))
    assert samples.temperature == (22.0,) * 120
    assert samples.altitude[10] == pytest.approx(41.0)


def test_metadata_name_is_the_fallback(tmp_path: Path) -> None:
    content = (
        b"<gpx creator='t'><metadata><name>Meta</name><desc>Meta desc</desc></metadata><trk><trkseg>"
        b"<trkpt lat='1' lon='1'><time>2026-06-20T08:00:00Z</time></trkpt>"
        b"<trkpt lat='1' lon='1'><time>2026-06-20T08:00:01Z</time></trkpt></trkseg></trk></gpx>"
    )

    recording = _decode_bytes(tmp_path, content)

    assert recording.name == "Meta"
    assert recording.description == "Meta desc"
    assert _only_session(recording).sport is None


def test_gpx_1_0_speed_child_and_namespaces(tmp_path: Path) -> None:
    content = (
        b'<g:gpx xmlns:g="http://www.topografix.com/GPX/1/0" creator="old"><g:trk><g:name>Old</g:name><g:trkseg>'
        b"<g:trkpt lat='1' lon='1'><g:time>2026-06-20T08:00:00Z</g:time><g:speed>2.5</g:speed></g:trkpt>"
        b"<g:trkpt lat='1' lon='1'><g:time>2026-06-20T08:00:01Z</g:time></g:trkpt></g:trkseg></g:trk></g:gpx>"
    )

    recording = _decode_bytes(tmp_path, content)

    assert _only_session(recording).samples.speed == (2.5, None)
    assert recording.name == "Old"


def test_bad_sensor_values_are_none_only_for_their_channel(tmp_path: Path) -> None:
    samples = _only_session(_decode_case(tmp_path, "bad_sensor_values")).samples

    assert len(samples) == 30
    heart_rate = list(samples.heart_rate)
    assert [heart_rate[i] for i in (3, 6, 9, 12)] == [None] * 4
    assert heart_rate[15] == 181
    assert all(value == 140 for i, value in enumerate(heart_rate) if i not in (3, 6, 9, 12, 15))
    assert samples.altitude[18] is None
    assert all(value == 25.0 for i, value in enumerate(samples.altitude) if i != 18)
    assert all(lat is not None for lat in samples.lat)


def test_infinite_heart_rate_is_none(tmp_path: Path) -> None:
    samples = _only_session(_decode_case(tmp_path, "infinite_heart_rate")).samples

    assert len(samples) == 30
    assert samples.heart_rate[10] is None
    assert samples.heart_rate.count(140) == 29


def test_mixed_time_formats_are_utc_and_ordered(tmp_path: Path) -> None:
    samples = _only_session(_decode_case(tmp_path, "mixed_time_formats")).samples

    assert samples.time == tuple(_START + timedelta(seconds=i) for i in range(60))
    assert all(time.tzinfo is UTC for time in samples.time)


def test_untimed_points_are_skipped(tmp_path: Path) -> None:
    samples = _only_session(_decode_case(tmp_path, "untimed_points")).samples

    assert len(samples) == 60
    assert all(value is not None for value in samples.heart_rate)


def test_out_of_order_points_are_sorted(tmp_path: Path) -> None:
    samples = _only_session(_decode_case(tmp_path, "out_of_order")).samples

    assert samples.time == tuple(_START + timedelta(seconds=i) for i in range(60))
    assert samples.lat == tuple(sorted(samples.lat))


def test_duplicate_timestamps_are_kept(tmp_path: Path) -> None:
    samples = _only_session(_decode_case(tmp_path, "duplicate_timestamps")).samples

    assert len(samples) == 60
    assert samples.time.count(_START + timedelta(seconds=20)) == 5


def test_null_island_is_kept(tmp_path: Path) -> None:
    samples = _only_session(_decode_case(tmp_path, "null_island")).samples

    assert samples.lat == (0.0,) * 60
    assert samples.lon == (0.0,) * 60


def test_out_of_range_position_and_negative_channels(tmp_path: Path) -> None:
    content = (
        b"<gpx creator='t'><trk><trkseg>"
        b"<trkpt lat='91' lon='10'><time>2026-06-20T08:00:00Z</time><ele>10000</ele>"
        b"<extensions><hr>-1</hr><cad>-2</cad><power>-3</power><temp>nan</temp></extensions></trkpt>"
        b"<trkpt lat='10' lon='181'><time>2026-06-20T08:00:01Z</time><extensions><power>200.6</power></extensions>"
        b"</trkpt><trkpt lat='-90' lon='-180'><time>2026-06-20T08:00:02</time></trkpt></trkseg></trk></gpx>"
    )

    samples = _only_session(_decode_bytes(tmp_path, content)).samples

    assert samples.lat == (None, None, -90.0)
    assert samples.lon == (None, None, -180.0)
    assert samples.altitude == (None, None, None)
    assert samples.heart_rate[0] is None
    assert samples.cadence[0] is None
    assert samples.power == (None, 201, None)
    assert samples.temperature[0] is None


def test_a_negative_speed_is_no_speed(tmp_path: Path) -> None:
    content = (
        b"<gpx creator='t'><trk><trkseg>"
        b"<trkpt lat='1' lon='1'><time>2026-06-20T08:00:00Z</time><extensions><speed>-1.5</speed></extensions></trkpt>"
        b"<trkpt lat='1' lon='1'><time>2026-06-20T08:00:01Z</time><extensions><speed>2.0</speed></extensions></trkpt>"
        b"</trkseg></trk></gpx>"
    )

    assert _only_session(_decode_bytes(tmp_path, content)).samples.speed == (None, 2.0)


def test_a_date_without_a_time_of_day_is_no_time(tmp_path: Path) -> None:
    content = (
        b"<gpx creator='t'><trk><trkseg>"
        b"<trkpt lat='1' lon='1'><time>2026-06-20</time></trkpt>"
        b"<trkpt lat='1' lon='1'><time>2026-06-20T08:00:00Z</time></trkpt>"
        b"<trkpt lat='1' lon='1'><time>2026-06-20T08:00:01Z</time></trkpt>"
        b"</trkseg></trk></gpx>"
    )

    assert _only_session(_decode_bytes(tmp_path, content)).samples.time == (
        datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC),
        datetime(2026, 6, 20, 8, 0, 1, tzinfo=UTC),
    )


def test_a_document_type_declaration_is_refused(tmp_path: Path) -> None:
    content = b"<?xml version='1.0'?><!DOCTYPE gpx><gpx creator='t'><trk><trkseg></trkseg></trk></gpx>"

    with pytest.raises(core_exceptions.InvalidInputError, match="Failed to parse GPX file"):
        _decode_bytes(tmp_path, content)


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("route_only", "no tracks"),
        ("not_gpx_root", "root element is not gpx"),
        ("malformed", "Failed to parse GPX file"),
        ("single_point", "at least two timed"),
    ],
)
def test_refused_synthetic_files(tmp_path: Path, name: str, message: str) -> None:
    with pytest.raises(core_exceptions.InvalidInputError, match=message):
        _decode_case(tmp_path, name)


def test_unreadable_file_is_a_processing_error(tmp_path: Path) -> None:
    with pytest.raises(core_exceptions.ProcessingError):
        gpx_decoder.decode_gpx(str(tmp_path / "missing.gpx"))


def test_entity_expansion_is_refused(tmp_path: Path) -> None:
    content = b'<?xml version="1.0"?><!DOCTYPE gpx [<!ENTITY a "b">]><gpx creator="t"><trk>&a;</trk></gpx>'

    with pytest.raises(core_exceptions.InvalidInputError):
        _decode_bytes(tmp_path, content)


def test_sample_limit_refuses_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(activity_file_import_recording, "MAX_SAMPLES_PER_FILE", 10)

    with pytest.raises(core_exceptions.InvalidInputError, match="more than 10 samples"):
        _decode_case(tmp_path, "power_extension")
