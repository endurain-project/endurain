"""Tests that the GPX encoder writes a recording ``gpx_decoder`` reads back with the same positioned samples."""

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.gpx_decoder as gpx_decoder
import modules.activities.activity_file_import.gpx_encoder as gpx_encoder
import modules.activities.activity_file_import.recording as recording
from tests.activities.activity_file_import import decoded

_T0 = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
_POSITIONED = sorted(
    name
    for name, rec in decoded.recordings().items()
    if any(lat is not None for session in rec.sessions for lat in session.samples.lat)
)
_UNPOSITIONED = sorted(set(decoded.recordings()) - set(_POSITIONED))


def _at(second: float) -> datetime:
    return _T0 + timedelta(seconds=second)


def _round_trip(tmp_path: Path, rec: recording.Recording) -> recording.Recording:
    """Encode a recording as GPX and decode the file."""
    path = tmp_path / "encoded.gpx"
    with path.open("wb") as target:
        gpx_encoder.encode_gpx(rec, target)
    return gpx_decoder.decode_gpx(str(path))


def _encoded(rec: recording.Recording) -> str:
    target = io.BytesIO()
    gpx_encoder.encode_gpx(rec, target)
    return target.getvalue().decode("utf-8")


def _session(builder: recording.SamplesBuilder, *, sport: str | None = "running", pauses=()) -> recording.Session:
    samples = builder.build()
    return recording.Session(sport=sport, start_time=samples.time[0], samples=samples, pauses=tuple(pauses))


def _builder() -> recording.SamplesBuilder:
    return recording.SamplesBuilder(recording.FileLimits())


def _expected_rows(rec: recording.Recording) -> list[tuple[object, ...]]:
    """Return the positioned samples of every session as GPX holds them, in time order."""
    rows: list[tuple[object, ...]] = []
    for session in rec.sessions:
        samples = session.samples
        for row in range(len(samples)):
            if samples.lat[row] is None or samples.lon[row] is None:
                continue
            heart_rate = samples.heart_rate[row]
            cadence = samples.cadence[row]
            rows.append(
                (
                    samples.time[row],
                    samples.lat[row],
                    samples.lon[row],
                    samples.altitude[row],
                    samples.speed[row],
                    heart_rate if heart_rate is not None and 1 <= heart_rate <= 255 else None,
                    round(cadence) if cadence is not None and round(cadence) <= 254 else None,
                    samples.power[row],
                    samples.temperature[row],
                )
            )
    return sorted(rows, key=lambda row: row[0])


def _rows(samples: recording.Samples) -> list[tuple[object, ...]]:
    return list(
        zip(
            samples.time,
            samples.lat,
            samples.lon,
            samples.altitude,
            samples.speed,
            samples.heart_rate,
            samples.cadence,
            samples.power,
            samples.temperature,
            strict=True,
        )
    )


def _expected_pauses(rec: recording.Recording) -> tuple[recording.Pause, ...]:
    """Return the pauses GPX holds: from the last point before each resume, or track end, to the first point after."""
    gaps: set[tuple[datetime, datetime]] = set()
    previous_end: datetime | None = None
    for session in rec.sessions:
        times = [
            time
            for time, lat, lon in zip(session.samples.time, session.samples.lat, session.samples.lon, strict=True)
            if lat is not None and lon is not None
        ]
        if not times:
            continue
        if previous_end is not None and times[0] > previous_end:
            gaps.add((previous_end, times[0]))
        for pause in session.pauses:
            before = [time for time in times if time < pause.end]
            after = [time for time in times if time >= pause.end]
            if before and after:
                gaps.add((before[-1], after[0]))
        previous_end = times[-1]
    return tuple(recording.Pause(start=start, end=end) for start, end in sorted(gaps))


@pytest.mark.parametrize("name", _POSITIONED)
def test_every_positioned_recording_reads_back_unchanged(tmp_path: Path, name: str) -> None:
    rec = decoded.recordings()[name]

    back = _round_trip(tmp_path, rec)

    assert len(back.sessions) == 1
    session = back.sessions[0]
    first_tracked = next(s for s in rec.sessions if any(lat is not None for lat in s.samples.lat))
    assert session.sport == first_tracked.sport
    assert _rows(session.samples) == _expected_rows(rec)
    assert all(distance is None for distance in session.samples.distance)
    assert session.pauses == _expected_pauses(rec)
    assert back.name == rec.name
    assert back.description == rec.description
    assert back.creator == "Endurain"


@pytest.mark.parametrize("name", _UNPOSITIONED)
def test_a_recording_without_positions_is_refused(name: str) -> None:
    with pytest.raises(core_exceptions.InvalidInputError, match="no positions to write as GPX"):
        gpx_encoder.encode_gpx(decoded.recordings()[name], io.BytesIO())


def test_samples_without_a_position_are_left_out(tmp_path: Path) -> None:
    builder = _builder()
    builder.append(_at(0), lat=41.0, lon=-8.0, heart_rate=120)
    builder.append(_at(1), heart_rate=121)
    builder.append(_at(2), lat=41.0001, lon=-8.0, heart_rate=122)
    rec = recording.Recording(format="fit", sessions=(_session(builder),))

    back = _round_trip(tmp_path, rec).sessions[0]

    assert back.samples.time == (_at(0), _at(2))
    assert back.samples.heart_rate == (120, 122)


def test_a_pause_starts_a_new_segment(tmp_path: Path) -> None:
    builder = _builder()
    for second in (0, 1, 2, 60, 61):
        builder.append(_at(second), lat=41.0 + second / 1e5, lon=-8.0)
    rec = recording.Recording(
        format="fit", sessions=(_session(builder, pauses=[recording.Pause(start=_at(2.5), end=_at(59.5))]),)
    )

    text = _encoded(rec)
    back = _round_trip(tmp_path, rec).sessions[0]

    assert text.count("<trkseg>") == 2
    assert back.pauses == (recording.Pause(start=_at(2), end=_at(60)),)


def test_each_session_is_its_own_track(tmp_path: Path) -> None:
    first, second = _builder(), _builder()
    first.append(_at(0), lat=41.0, lon=-8.0)
    first.append(_at(1), lat=41.0001, lon=-8.0)
    second.append(_at(10), lat=41.0002, lon=-8.0)
    second.append(_at(11), lat=41.0003, lon=-8.0)
    rec = recording.Recording(
        format="fit", sessions=(_session(first, sport="swimming"), _session(second, sport="cycling"))
    )

    text = _encoded(rec)
    back = _round_trip(tmp_path, rec).sessions[0]

    assert text.count("<trk>") == 2
    assert "<type>swimming</type>" in text
    assert "<type>cycling</type>" in text
    assert back.pauses == (recording.Pause(start=_at(1), end=_at(10)),)


def test_values_the_extension_schema_cannot_hold_are_left_out() -> None:
    builder = _builder()
    builder.append(_at(0), lat=41.0, lon=-8.0, heart_rate=0, cadence=300.0, power=70_000)
    builder.append(_at(1), lat=41.0, lon=-8.0, heart_rate=256, cadence=89.6, power=250)
    text = _encoded(recording.Recording(format="fit", sessions=(_session(builder),)))

    assert "<gpxtpx:hr>" not in text
    assert text.count("<gpxtpx:cad>") == 1
    assert "<gpxtpx:cad>90</gpxtpx:cad>" in text
    assert text.count("<gpxpx:PowerInWatts>") == 1
    assert "<gpxpx:PowerInWatts>250</gpxpx:PowerInWatts>" in text


def test_a_sample_with_only_a_position_has_no_extensions() -> None:
    builder = _builder()
    builder.append(_at(0), lat=41.0, lon=-8.0)
    builder.append(_at(1), lat=41.0, lon=-8.0, altitude=10.5)
    text = _encoded(recording.Recording(format="fit", sessions=(_session(builder, sport=None),)))

    assert "<extensions>" not in text
    assert "<type>" not in text
    assert "<ele>10.5</ele>" in text


def test_name_and_description_are_escaped(tmp_path: Path) -> None:
    builder = _builder()
    builder.append(_at(0), lat=41.0, lon=-8.0)
    builder.append(_at(1), lat=41.0, lon=-8.0)
    rec = recording.Recording(
        format="fit", sessions=(_session(builder),), name="Run <fast> & far\x00", description="Line 1\nLine 2"
    )

    back = _round_trip(tmp_path, rec)

    assert back.name == "Run <fast> & far"
    assert back.description == "Line 1\nLine 2"
