"""Tests for the TCX decoder: what a recording holds for real device files and synthetic edge cases."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.recording as activity_file_import_recording
import modules.activities.activity_file_import.tcx_decoder as tcx_decoder
from tests.activities.activity_file_import import synthetic_files

_FIXTURES = Path(__file__).parent / "fixtures"
_REAL = sorted(_FIXTURES.rglob("*.tcx"))
_NO_POSITION = {"pool_swim", "strength", "hiit", "treadmill_run", "indoor_ride"}
_NO_TIME_MESSAGE = "Invalid TCX file - no activity start or end time found"


def _decode_case(tmp_path: Path, name: str) -> activity_file_import_recording.Recording:
    """Write a synthetic case to a file and decode it."""
    path = tmp_path / "case.tcx"
    path.write_bytes(synthetic_files.CASES[f"tcx/{name}.tcx"]())
    return tcx_decoder.decode_tcx(str(path))


def _decode_text(tmp_path: Path, document: str) -> activity_file_import_recording.Recording:
    """Write TCX text to a file and decode it."""
    path = tmp_path / "text.tcx"
    path.write_text(document, encoding="utf-8")
    return tcx_decoder.decode_tcx(str(path))


def _trackpoints(text: str) -> list[str]:
    """Return the trackpoint blocks of a TCX text that have a ``Time``."""
    return [block for block in re.findall(r"<Trackpoint>.*?</Trackpoint>", text, re.S) if "<Time>" in block]


@pytest.mark.parametrize("path", _REAL, ids=lambda path: path.parent.name)
def test_real_files_keep_laps_samples_and_positions(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    recording = tcx_decoder.decode_tcx(str(path))
    session = recording.sessions[0]
    blocks = _trackpoints(text)
    assert recording.format == "tcx"
    assert len(recording.sessions) == len(re.findall(r"<Activity\b", text))
    assert session.sport == re.search(r'Sport="(\w+)"', text).group(1)
    assert len(session.laps) == len(re.findall(r"<Lap\b", text))
    assert len(session.samples) == len(blocks)
    expected = sum("<LatitudeDegrees>" in block for block in blocks)
    assert sum(lat is not None for lat in session.samples.lat) == expected
    assert (expected == 0) == (path.parent.name in _NO_POSITION)
    assert list(session.samples.time) == sorted(session.samples.time)
    assert all(moment.tzinfo is not None for moment in session.samples.time)


def test_lost_fix_keeps_every_sample(tmp_path: Path) -> None:
    session = _decode_case(tmp_path, "lost_fix").sessions[0]
    samples = session.samples
    assert len(samples) == 120
    missing = [index for index, lat in enumerate(samples.lat) if lat is None]
    assert missing == list(range(45, 75))
    assert all(samples.lon[index] is None for index in missing)
    assert all(samples.heart_rate[index] is not None and samples.power[index] is not None for index in missing)
    assert session.summary.calories == 60


def test_multi_activity_is_one_session_per_activity(tmp_path: Path) -> None:
    recording = _decode_case(tmp_path, "multi_activity")
    run, ride = recording.sessions
    assert (run.sport, ride.sport) == ("Running", "Biking")
    assert (len(run.samples), len(ride.samples)) == (60, 60)
    assert ride.start_time == run.start_time + timedelta(hours=1)
    assert ride.samples.time[0] == ride.start_time
    assert (run.summary.calories, ride.summary.calories) == (30, 25)


def test_short_laps_are_kept(tmp_path: Path) -> None:
    session = _decode_case(tmp_path, "short_laps").sessions[0]
    assert len(session.laps) == 5
    assert len(session.samples) == 183


def test_ride_power_reads_channels_and_lap_extension(tmp_path: Path) -> None:
    session = _decode_case(tmp_path, "ride_power").sessions[0]
    samples = session.samples
    assert len(session.laps) == 3
    assert all(lap.avg_power == 205 and lap.total_calories == 40 for lap in session.laps)
    assert samples.power[0] == 190
    assert samples.speed[0] == 7.0
    assert samples.cadence[0] == 80.0
    assert samples.altitude[1] == 40.1
    assert session.summary.calories == 120


def test_lap_summary_only_is_refused(tmp_path: Path) -> None:
    with pytest.raises(core_exceptions.InvalidInputError, match=_NO_TIME_MESSAGE):
        _decode_case(tmp_path, "lap_summary_only")


def test_missing_watts_is_none_where_absent(tmp_path: Path) -> None:
    samples = _decode_case(tmp_path, "missing_watts").sessions[0].samples
    assert len(samples) == 90
    assert [power is None for power in samples.power] == [index % 3 == 0 for index in range(90)]
    assert all(rate is None for rate in samples.heart_rate)


def test_paused_keeps_the_gap_without_samples(tmp_path: Path) -> None:
    session = _decode_case(tmp_path, "paused").sessions[0]
    assert len(session.samples) == 120
    gap = session.samples.time[60] - session.samples.time[59]
    assert gap > timedelta(minutes=9)
    assert session.pauses == ()


def test_track_boundary_with_a_gap_is_a_pause(tmp_path: Path) -> None:
    def point(second: int) -> str:
        return f"<Trackpoint><Time>2026-06-20T08:00:{second:02d}Z</Time></Trackpoint>"

    document = (
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"><Activities>'
        '<Activity Sport="Running"><Id>2026-06-20T08:00:00Z</Id><Lap StartTime="2026-06-20T08:00:00Z">'
        f"<Track>{point(0)}{point(10)}</Track><Track>{point(10)}{point(20)}</Track><Track>{point(40)}</Track>"
        "</Lap></Activity></Activities></TrainingCenterDatabase>"
    )
    session = _decode_text(tmp_path, document).sessions[0]
    assert len(session.samples) == 5
    assert session.pauses == (
        activity_file_import_recording.Pause(
            start=datetime(2026, 6, 20, 8, 0, 20, tzinfo=UTC), end=datetime(2026, 6, 20, 8, 0, 40, tzinfo=UTC)
        ),
    )


def test_a_lap_boundary_is_not_a_pause(tmp_path: Path) -> None:
    def point(second: int) -> str:
        return f"<Trackpoint><Time>2026-06-20T08:00:{second:02d}Z</Time></Trackpoint>"

    def lap(first: int, last: int) -> str:
        points = "".join(point(second) for second in range(first, last + 1))
        return f'<Lap StartTime="2026-06-20T08:00:{first:02d}Z"><Track>{points}</Track></Lap>'

    document = (
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"><Activities>'
        f'<Activity Sport="Running"><Id>2026-06-20T08:00:00Z</Id>{lap(0, 9)}{lap(10, 19)}{lap(50, 59)}</Activity>'
        "</Activities></TrainingCenterDatabase>"
    )
    session = _decode_text(tmp_path, document).sessions[0]
    assert len(session.samples) == 30
    assert session.pauses == ()


def test_subsecond_keeps_milliseconds(tmp_path: Path) -> None:
    session = _decode_case(tmp_path, "subsecond").sessions[0]
    assert session.samples.time[0] == datetime(2026, 6, 20, 8, 0, 0, 250000, tzinfo=UTC)
    assert session.samples.time[1] - session.samples.time[0] == timedelta(seconds=1)


def test_other_sport_is_kept_as_the_file_names_it(tmp_path: Path) -> None:
    session = _decode_case(tmp_path, "other_sport_gps").sessions[0]
    assert session.sport == "Other"
    assert all(lat is not None for lat in session.samples.lat)


def test_malformed_is_refused(tmp_path: Path) -> None:
    with pytest.raises(core_exceptions.InvalidInputError):
        _decode_case(tmp_path, "malformed")


def test_wrong_root_and_no_activity_are_refused(tmp_path: Path) -> None:
    with pytest.raises(core_exceptions.InvalidInputError):
        _decode_text(tmp_path, '<?xml version="1.0"?><gpx><trk/></gpx>')
    with pytest.raises(core_exceptions.InvalidInputError):
        _decode_text(tmp_path, "<TrainingCenterDatabase><Activities/></TrainingCenterDatabase>")


def test_missing_file_is_a_processing_error(tmp_path: Path) -> None:
    with pytest.raises(core_exceptions.ProcessingError):
        tcx_decoder.decode_tcx(str(tmp_path / "absent.tcx"))


def _activity(*points: str, activity_attrs: str = 'Sport="Running"', lap_body: str = "", extra: str = "") -> str:
    """Build a one-lap TCX document around trackpoint XML."""
    return (
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" '
        'xmlns:x="http://www.garmin.com/xmlschemas/ActivityExtension/v2"><Activities>'
        f"<Activity {activity_attrs}><Id>2026-06-20T08:00:00+02:00</Id>"
        f'<Lap StartTime="2026-06-20T08:00:00">{lap_body}<Track>{"".join(points)}</Track></Lap>{extra}'
        "</Activity></Activities></TrainingCenterDatabase>"
    )


def test_values_are_cleaned_per_channel(tmp_path: Path) -> None:
    points = (
        "<Trackpoint><Time>2026-06-20T08:00:02</Time><Position><LatitudeDegrees>95</LatitudeDegrees>"
        "<LongitudeDegrees>1</LongitudeDegrees></Position><HeartRateBpm><Value>-5</Value></HeartRateBpm>"
        "<Cadence>-1</Cadence><Extensions><x:TPX><x:Watts>-3</x:Watts><x:Speed>nan</x:Speed></x:TPX></Extensions>"
        "</Trackpoint>",
        "<Trackpoint><Time>2026-06-20T08:00:01Z</Time><AltitudeMeters>abc</AltitudeMeters>"
        "<Extensions><x:TPX><x:RunCadence>85</x:RunCadence></x:TPX></Extensions></Trackpoint>",
        "<Trackpoint><Time>2026-06-20T08:00:03Z</Time></Trackpoint>",
        "<Trackpoint><Time>not a time</Time><HeartRateBpm><Value>90</Value></HeartRateBpm></Trackpoint>",
    )
    session = _decode_text(tmp_path, _activity(*points)).sessions[0]
    samples = session.samples
    assert len(samples) == 3
    assert samples.time == (
        datetime(2026, 6, 20, 8, 0, 1, tzinfo=UTC),
        datetime(2026, 6, 20, 8, 0, 2, tzinfo=UTC),
        datetime(2026, 6, 20, 8, 0, 3, tzinfo=UTC),
    )
    assert samples.cadence == (85.0, None, None)
    assert samples.altitude == (None, None, None)
    assert samples.lat == (None, None, None)
    assert samples.heart_rate == (None, None, None)
    assert samples.power == (None, None, None)
    assert samples.speed == (None, None, None)
    assert session.start_time == datetime(2026, 6, 20, 6, 0, tzinfo=UTC)


def test_lap_fields_notes_and_creator(tmp_path: Path) -> None:
    lap_body = (
        "<TotalTimeSeconds>60.5</TotalTimeSeconds><DistanceMeters>200</DistanceMeters>"
        "<MaximumSpeed>4.5</MaximumSpeed><Calories>12</Calories>"
        "<AverageHeartRateBpm><Value>140</Value></AverageHeartRateBpm>"
        "<MaximumHeartRateBpm><Value>170</Value></MaximumHeartRateBpm>"
        "<Intensity>Resting</Intensity><TriggerMethod>Distance</TriggerMethod><Cadence>80</Cadence>"
        "<Extensions><x:LX><x:AvgSpeed>3.3</x:AvgSpeed><x:AvgWatts>200</x:AvgWatts><x:MaxWatts>300</x:MaxWatts>"
        "<x:MaxRunCadence>95</x:MaxRunCadence><x:Steps>150</x:Steps></x:LX></Extensions>"
    )
    point = "<Trackpoint><Time>2026-06-20T08:00:00Z</Time></Trackpoint>"
    recording = _decode_text(
        tmp_path,
        _activity(point, lap_body=lap_body, extra="<Notes>felt good</Notes><Creator><Name>Forerunner</Name></Creator>"),
    )
    lap = recording.sessions[0].laps[0]
    assert recording.description == "felt good"
    assert recording.creator == "Forerunner"
    assert recording.manufacturer is None
    assert (lap.total_timer_time, lap.total_elapsed_time, lap.total_distance) == (60.5, None, 200.0)
    assert (lap.max_speed, lap.avg_speed, lap.total_calories) == (4.5, 3.3, 12)
    assert (lap.avg_heart_rate, lap.max_heart_rate) == (140, 170)
    assert (lap.intensity, lap.lap_trigger) == ("resting", "distance")
    assert (lap.avg_cadence, lap.max_cadence, lap.avg_power, lap.max_power, lap.total_cycles) == (
        80,
        95,
        200,
        300,
        150,
    )


def test_lap_cadence_element_is_left_to_the_samples_when_its_trackpoints_carry_cadence(tmp_path: Path) -> None:
    # Garmin Connect writes the lap's highest cadence in <Cadence>, so it is not read as the average.
    lap_body = "<TotalTimeSeconds>60</TotalTimeSeconds><Cadence>129</Cadence>"
    point = "<Trackpoint><Time>2026-06-20T08:00:00Z</Time><Cadence>70</Cadence></Trackpoint>"
    lap = _decode_text(tmp_path, _activity(point, lap_body=lap_body)).sessions[0].laps[0]
    assert (lap.avg_cadence, lap.max_cadence) == (None, None)


def test_lap_cadence_element_is_the_average_when_its_trackpoints_carry_none(tmp_path: Path) -> None:
    lap_body = "<TotalTimeSeconds>60</TotalTimeSeconds><Cadence>88</Cadence>"
    point = "<Trackpoint><Time>2026-06-20T08:00:00Z</Time></Trackpoint>"
    lap = _decode_text(tmp_path, _activity(point, lap_body=lap_body)).sessions[0].laps[0]
    assert (lap.avg_cadence, lap.max_cadence) == (88, None)


def test_lap_bike_cadence_maximum_comes_from_the_extension(tmp_path: Path) -> None:
    lap_body = (
        "<TotalTimeSeconds>60</TotalTimeSeconds>"
        "<Extensions><x:LX><x:MaxBikeCadence>110</x:MaxBikeCadence></x:LX></Extensions>"
    )
    point = "<Trackpoint><Time>2026-06-20T08:00:00Z</Time><Cadence>90</Cadence></Trackpoint>"
    lap = _decode_text(tmp_path, _activity(point, lap_body=lap_body)).sessions[0].laps[0]
    assert (lap.avg_cadence, lap.max_cadence) == (None, 110)


def test_session_start_falls_back_to_first_lap(tmp_path: Path) -> None:
    document = _activity("<Trackpoint><Time>2026-06-20T08:00:00Z</Time></Trackpoint>").replace(
        "<Id>2026-06-20T08:00:00+02:00</Id>", ""
    )
    assert _decode_text(tmp_path, document).sessions[0].start_time == datetime(2026, 6, 20, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    ("limit", "value", "document"),
    [
        (
            "MAX_SAMPLES_PER_FILE",
            2,
            _activity(*(f"<Trackpoint><Time>2026-06-20T08:00:0{i}Z</Time></Trackpoint>" for i in range(3))),
        ),
        (
            "MAX_SESSIONS_PER_FILE",
            1,
            _activity("<Trackpoint><Time>2026-06-20T08:00:00Z</Time></Trackpoint>").replace(
                "</Activities>",
                _activity("<Trackpoint><Time>2026-06-20T09:00:00Z</Time></Trackpoint>").split("<Activities>")[1],
            ),
        ),
    ],
)
def test_file_limits_are_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, limit: str, value: int, document: str
) -> None:
    monkeypatch.setattr(activity_file_import_recording, limit, value)
    with pytest.raises(core_exceptions.InvalidInputError, match="more than"):
        _decode_text(tmp_path, document)
