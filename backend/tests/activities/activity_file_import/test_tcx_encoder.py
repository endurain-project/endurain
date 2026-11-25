"""Tests that the TCX encoder writes a recording ``tcx_decoder`` reads back with the same samples, laps and pauses."""

import bisect
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import modules.activities.activity.constants as activity_constants
import modules.activities.activity_file_import.recording as recording
import modules.activities.activity_file_import.tcx_decoder as tcx_decoder
import modules.activities.activity_file_import.tcx_encoder as tcx_encoder
from tests.activities.activity_file_import import decoded

_T0 = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
_WITH_SAMPLES = sorted(
    name for name, rec in decoded.recordings().items() if all(len(session.samples) for session in rec.sessions)
)
_TRIGGERS_KEPT = {"manual", "distance", "time"}


def _at(second: float) -> datetime:
    return _T0 + timedelta(seconds=second)


def _round_trip(tmp_path: Path, rec: recording.Recording) -> recording.Recording:
    """Encode a recording as TCX and decode the file."""
    path = tmp_path / "encoded.tcx"
    with path.open("wb") as target:
        tcx_encoder.encode_tcx(rec, target)
    return tcx_decoder.decode_tcx(str(path))


def _encoded(rec: recording.Recording) -> str:
    target = io.BytesIO()
    tcx_encoder.encode_tcx(rec, target)
    return target.getvalue().decode("utf-8")


def _builder() -> recording.SamplesBuilder:
    return recording.SamplesBuilder(recording.FileLimits())


def _recording(session: recording.Session) -> recording.Recording:
    return recording.Recording(format="fit", sessions=(session,))


def _bucket(sport: str | None) -> str | None:
    """Return the run or bike bucket of a sport, ``None`` for any other."""
    activity_type = activity_constants.define_activity_type(sport) if sport else None
    for bucket in ("run", "bike"):
        if activity_type in activity_constants.ACTIVITY_TYPES_BY_SPORT[bucket]:
            return bucket
    return None


def _heart_rate(value: int | None) -> int | None:
    return value if value is not None and 1 <= value <= 255 else None


def _cadence(value: float | None) -> int | None:
    return round(value) if value is not None and round(value) <= 254 else None


def _expected_rows(samples: recording.Samples) -> list[tuple[object, ...]]:
    """Return a session's samples as TCX holds them."""
    return [
        (
            samples.time[row],
            samples.lat[row],
            samples.lon[row],
            samples.altitude[row],
            samples.distance[row],
            samples.speed[row],
            _heart_rate(samples.heart_rate[row]),
            _cadence(samples.cadence[row]),
            samples.power[row],
            None,
        )
        for row in range(len(samples))
    ]


def _rows(samples: recording.Samples) -> list[tuple[object, ...]]:
    return list(
        zip(
            samples.time,
            samples.lat,
            samples.lon,
            samples.altitude,
            samples.distance,
            samples.speed,
            samples.heart_rate,
            samples.cadence,
            samples.power,
            samples.temperature,
            strict=True,
        )
    )


def _expected_pauses(session: recording.Session) -> tuple[recording.Pause, ...]:
    """Return the pauses TCX holds: a resume inside a lap, from the last sample before it to the first after."""
    times = session.samples.time
    starts = [lap.start_time for lap in session.laps] or [session.start_time]

    def lap_of(time: datetime) -> int:
        return max(bisect.bisect_right(starts, time) - 1, 0)

    gaps: set[tuple[datetime, datetime]] = set()
    for pause in session.pauses:
        resumed = bisect.bisect_left(times, pause.end)
        if 0 < resumed < len(times) and lap_of(times[resumed - 1]) == lap_of(times[resumed]):
            gaps.add((times[resumed - 1], times[resumed]))
    return tuple(recording.Pause(start=start, end=end) for start, end in sorted(gaps))


def _assert_device_lap(back: recording.Lap, lap: recording.Lap, running: bool) -> None:
    """Assert a decoded lap holds what TCX keeps of the device lap it was written from."""
    timer = lap.total_timer_time if lap.total_timer_time is not None else lap.total_elapsed_time
    assert back.start_time == lap.start_time
    assert back.total_timer_time == (timer or 0.0)
    assert back.total_distance == (lap.total_distance or 0.0)
    assert back.max_speed == lap.max_speed
    assert back.avg_speed == lap.avg_speed
    assert back.total_calories == (lap.total_calories or 0)
    assert back.avg_heart_rate == _heart_rate(lap.avg_heart_rate)
    assert back.max_heart_rate == _heart_rate(lap.max_heart_rate)
    assert back.avg_power == lap.avg_power
    assert back.max_power == lap.max_power
    assert back.max_cadence == _cadence(lap.max_cadence)
    assert back.intensity == ("resting" if lap.intensity in {"rest", "resting"} else "active")
    if lap.lap_trigger in _TRIGGERS_KEPT:
        assert back.lap_trigger == lap.lap_trigger
    if running:
        assert back.avg_cadence == _cadence(lap.avg_cadence)
        assert back.total_cycles == lap.total_cycles


@pytest.mark.parametrize("name", _WITH_SAMPLES)
def test_every_recording_reads_back_unchanged(tmp_path: Path, name: str) -> None:
    rec = decoded.recordings()[name]

    back = _round_trip(tmp_path, rec)

    assert len(back.sessions) == len(rec.sessions)
    assert back.description == rec.description
    for session, read in zip(rec.sessions, back.sessions, strict=True):
        bucket = _bucket(session.sport)
        assert read.sport == {"run": "Running", "bike": "Biking"}.get(bucket or "", "Other")
        assert read.start_time == session.start_time
        assert _rows(read.samples) == _expected_rows(session.samples)
        assert read.pauses == _expected_pauses(session)
        if session.laps:
            assert len(read.laps) == len(session.laps)
            for lap, read_lap in zip(session.laps, read.laps, strict=True):
                _assert_device_lap(read_lap, lap, bucket == "run")
            assert read.summary.calories == sum(lap.total_calories or 0 for lap in session.laps)
        else:
            assert len(read.laps) == 1
            assert read.laps[0].start_time == session.start_time
            assert read.summary.calories == (session.summary.calories or 0)


def test_a_session_without_laps_is_one_lap_of_its_totals(tmp_path: Path) -> None:
    builder = _builder()
    for second in (0, 10, 20, 80, 90):
        builder.append(_at(second), distance=second * 3.0)
    samples = builder.build()
    session = recording.Session(
        sport="cycling",
        start_time=_at(0),
        samples=samples,
        pauses=(recording.Pause(start=_at(25), end=_at(75)),),
        summary=recording.DeviceSummary(calories=55, avg_heart_rate=140, max_speed=9.5),
    )

    lap = _round_trip(tmp_path, _recording(session)).sessions[0].laps[0]

    assert lap.start_time == _at(0)
    assert lap.total_timer_time == 40.0
    assert lap.total_distance == 270.0
    assert lap.total_calories == 55
    assert lap.avg_heart_rate == 140
    assert lap.max_speed == 9.5
    assert lap.intensity == "active"
    assert lap.lap_trigger == "manual"


def test_the_device_timer_and_distance_win_for_a_session_without_laps(tmp_path: Path) -> None:
    builder = _builder()
    builder.append(_at(0), distance=0.0)
    builder.append(_at(100), distance=300.0)
    session = recording.Session(
        sport="running",
        start_time=_at(0),
        samples=builder.build(),
        summary=recording.DeviceSummary(total_timer_time=95.5, distance=310.0),
    )

    lap = _round_trip(tmp_path, _recording(session)).sessions[0].laps[0]

    assert lap.total_timer_time == 95.5
    assert lap.total_distance == 310.0
    assert lap.total_calories == 0


def test_running_cadence_goes_in_the_extension(tmp_path: Path) -> None:
    builder = _builder()
    builder.append(_at(0), cadence=84.6)
    builder.append(_at(1), cadence=85.0)
    lap = recording.Lap(
        start_time=_at(0), total_timer_time=1.0, avg_cadence=85, max_cadence=88, total_cycles=170, intensity="active"
    )
    session = recording.Session(sport="running", start_time=_at(0), samples=builder.build(), laps=(lap,))

    text = _encoded(_recording(session))
    back = _round_trip(tmp_path, _recording(session)).sessions[0]

    assert "<Cadence>" not in text
    assert "<ns3:RunCadence>85</ns3:RunCadence>" in text
    assert back.samples.cadence == (85.0, 85.0)
    assert (back.laps[0].avg_cadence, back.laps[0].max_cadence, back.laps[0].total_cycles) == (85, 88, 170)


def test_bike_cadence_is_the_trackpoint_and_lap_cadence_element(tmp_path: Path) -> None:
    builder = _builder()
    builder.append(_at(0), cadence=90.0)
    builder.append(_at(1), cadence=92.0)
    lap = recording.Lap(start_time=_at(0), total_timer_time=1.0, avg_cadence=91, max_cadence=95, total_cycles=2)
    session = recording.Session(sport="cycling", start_time=_at(0), samples=builder.build(), laps=(lap,))

    text = _encoded(_recording(session))

    assert "<Cadence>90</Cadence>" in text
    assert "<Cadence>91</Cadence><TriggerMethod>" in text
    assert "<ns3:MaxBikeCadence>95</ns3:MaxBikeCadence>" in text
    assert "RunCadence" not in text
    assert "<ns3:Steps>" not in text


def test_a_lap_with_no_sample_cadence_reads_its_average_back(tmp_path: Path) -> None:
    builder = _builder()
    builder.append(_at(0), heart_rate=120)
    builder.append(_at(1), heart_rate=121)
    lap = recording.Lap(start_time=_at(0), total_timer_time=1.0, avg_cadence=78)
    session = recording.Session(sport="cycling", start_time=_at(0), samples=builder.build(), laps=(lap,))

    assert _round_trip(tmp_path, _recording(session)).sessions[0].laps[0].avg_cadence == 78


@pytest.mark.parametrize(
    ("sport", "expected"),
    [("running", "Running"), ("cycling", "Biking"), ("Biking", "Biking"), ("swimming", "Other"), (None, "Other")],
)
def test_the_sport_is_named_as_tcx_names_it(sport: str | None, expected: str) -> None:
    builder = _builder()
    builder.append(_at(0))
    session = recording.Session(sport=sport, start_time=_at(0), samples=builder.build())

    assert f'<Activity Sport="{expected}">' in _encoded(_recording(session))


@pytest.mark.parametrize(
    ("intensity", "trigger", "expected"),
    [
        ("rest", "position_lap", "<Intensity>Resting</Intensity><TriggerMethod>Location</TriggerMethod>"),
        ("warmup", "heart_rate", "<Intensity>Active</Intensity><TriggerMethod>HeartRate</TriggerMethod>"),
        (None, "session_end", "<Intensity>Active</Intensity><TriggerMethod>Manual</TriggerMethod>"),
    ],
)
def test_lap_intensity_and_trigger_are_named_as_tcx_names_them(intensity, trigger, expected) -> None:
    builder = _builder()
    builder.append(_at(0))
    lap = recording.Lap(start_time=_at(0), intensity=intensity, lap_trigger=trigger)
    session = recording.Session(sport="running", start_time=_at(0), samples=builder.build(), laps=(lap,))

    text = _encoded(_recording(session))

    assert expected in text
    assert "<TotalTimeSeconds>0.0</TotalTimeSeconds><DistanceMeters>0.0</DistanceMeters><Calories>0</Calories>" in text


def test_samples_before_the_first_lap_go_in_it_and_each_lap_holds_its_own(tmp_path: Path) -> None:
    builder = _builder()
    for second in range(6):
        builder.append(_at(second))
    laps = (recording.Lap(start_time=_at(1), total_timer_time=2.0), recording.Lap(start_time=_at(3)))
    session = recording.Session(sport="running", start_time=_at(0), samples=builder.build(), laps=laps)

    text = _encoded(_recording(session))
    back = _round_trip(tmp_path, _recording(session)).sessions[0]

    first, second = text.split("<Lap ")[1:]
    assert first.count("<Trackpoint>") == 3
    assert second.count("<Trackpoint>") == 3
    assert len(back.samples) == 6
    assert back.pauses == ()


def test_a_pause_inside_a_lap_is_a_new_track(tmp_path: Path) -> None:
    builder = _builder()
    for second in (0, 1, 60, 61):
        builder.append(_at(second))
    session = recording.Session(
        sport="running",
        start_time=_at(0),
        samples=builder.build(),
        pauses=(recording.Pause(start=_at(1.5), end=_at(59)),),
        laps=(recording.Lap(start_time=_at(0), total_timer_time=3.0),),
    )

    text = _encoded(_recording(session))
    back = _round_trip(tmp_path, _recording(session)).sessions[0]

    assert text.count("<Track>") == 2
    assert back.pauses == (recording.Pause(start=_at(1), end=_at(60)),)


def test_a_lap_without_samples_has_no_track() -> None:
    builder = _builder()
    builder.append(_at(0))
    laps = (recording.Lap(start_time=_at(0)), recording.Lap(start_time=_at(10)))
    session = recording.Session(sport="running", start_time=_at(0), samples=builder.build(), laps=laps)

    assert _encoded(_recording(session)).count("<Track>") == 1


def test_values_the_schema_cannot_hold_are_left_out() -> None:
    builder = _builder()
    builder.append(_at(0), heart_rate=0, cadence=255.0, power=70_000)
    lap = recording.Lap(start_time=_at(0), avg_heart_rate=0, max_power=70_000, total_calories=70_000)
    session = recording.Session(sport="cycling", start_time=_at(0), samples=builder.build(), laps=(lap,))

    text = _encoded(_recording(session))

    assert "HeartRateBpm" not in text
    assert "Cadence" not in text
    assert "Watts" not in text
    assert "<Calories>0</Calories>" in text


def test_the_description_is_each_activitys_notes(tmp_path: Path) -> None:
    builder = _builder()
    builder.append(_at(0))
    session = recording.Session(sport="running", start_time=_at(0), samples=builder.build())
    rec = recording.Recording(format="fit", sessions=(session, session), description="Hills & <wind>")

    text = _encoded(rec)

    assert text.count("<Notes>Hills &amp; &lt;wind&gt;</Notes>") == 2
    assert _round_trip(tmp_path, rec).description == "Hills & <wind>"
