"""Tests for the activities assembled from TCX files: decode a document, assemble it, read the payload."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import modules.activities.activity_file_import.assembly as assembly
import modules.activities.activity_file_import.parser_utils as parser_utils
from tests.activities.activity_file_import.assembled import assemble_tcx

_T0 = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
_ROOT = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" '
    'xmlns:x="http://www.garmin.com/xmlschemas/ActivityExtension/v2">'
)


def _stamp(seconds: float) -> str:
    """Return the TCX time ``seconds`` after the start of the activity."""
    return (_T0 + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tp(
    seconds: float,
    *,
    lat: float | None = None,
    lon: float | None = None,
    ele: float | None = None,
    hr: int | None = None,
    cad: int | None = None,
    power: int | None = None,
    speed: float | None = None,
    run_cad: int | None = None,
    stamp: str | None = None,
) -> str:
    """Return one <Trackpoint> recorded ``seconds`` after the start of the activity."""
    position = ""
    if lat is not None or lon is not None:
        position = (
            "<Position>"
            + (f"<LatitudeDegrees>{lat}</LatitudeDegrees>" if lat is not None else "")
            + (f"<LongitudeDegrees>{lon}</LongitudeDegrees>" if lon is not None else "")
            + "</Position>"
        )
    altitude = f"<AltitudeMeters>{ele}</AltitudeMeters>" if ele is not None else ""
    heart_rate = f"<HeartRateBpm><Value>{hr}</Value></HeartRateBpm>" if hr is not None else ""
    cadence = f"<Cadence>{cad}</Cadence>" if cad is not None else ""
    tpx = (
        (f"<x:Watts>{power}</x:Watts>" if power is not None else "")
        + (f"<x:Speed>{speed}</x:Speed>" if speed is not None else "")
        + (f"<x:RunCadence>{run_cad}</x:RunCadence>" if run_cad is not None else "")
    )
    extensions = f"<Extensions><x:TPX>{tpx}</x:TPX></Extensions>" if tpx else ""
    return (
        f"<Trackpoint><Time>{stamp or _stamp(seconds)}</Time>{position}{altitude}{heart_rate}{cadence}{extensions}"
        "</Trackpoint>"
    )


def _lap(start: float, points: str, body: str = "") -> str:
    """Return a <Lap> starting ``start`` seconds after the start of the activity."""
    return f'<Lap StartTime="{_stamp(start)}">{body}<Track>{points}</Track></Lap>'


def _document(*laps: str, sport: str = "Running", activity_id: str | None = None) -> str:
    """Return a TCX document of one activity holding the laps."""
    identifier = activity_id or _stamp(0)
    return (
        f'{_ROOT}<Activities><Activity Sport="{sport}"><Id>{identifier}</Id>{"".join(laps)}</Activity></Activities>'
        "</TrainingCenterDatabase>"
    )


def _on_off_watts(seconds: int) -> list[int]:
    """Return 1 Hz power alternating 30 s of 400 W and 30 s of 100 W."""
    return [400 if (second // 30) % 2 == 0 else 100 for second in range(seconds)]


def _coggan_np(watts: list[int]) -> float:
    """Return the normalized power of a 1 Hz list in plain Python: 30 s rolling mean, 4th-power mean, 4th root."""
    rolling = [sum(watts[i : i + 30]) / 30 for i in range(len(watts) - 29)]
    return (sum(w**4 for w in rolling) / len(rolling)) ** 0.25


def _assemble(tmp_path: Path, document: str, **kwargs: Any) -> list[assembly.ActivityFilePayload]:
    """Write a document to a file and assemble it."""
    path = tmp_path / "activity.tcx"
    path.write_text(document, encoding="utf-8")
    return assemble_tcx(str(path), **kwargs)


def _one(tmp_path: Path, points: str, *, seconds: int | None = 180, distance: float | None = None, **kwargs: Any):
    """Assemble a one-lap running file; the lap's timer and distance are optional."""
    body = f"<TotalTimeSeconds>{seconds}</TotalTimeSeconds>" if seconds is not None else ""
    body += f"<DistanceMeters>{distance}</DistanceMeters>" if distance is not None else ""
    sport = str(kwargs.pop("sport", "Running"))
    (payload,) = _assemble(tmp_path, _document(_lap(0, points, body), sport=sport), **kwargs)
    return payload


class TestUtcAndTimes:
    """Offset times become UTC; start and end come from the file's own times."""

    def test_offset_times_are_stored_as_utc(self, tmp_path: Path) -> None:
        """Offset-bearing trackpoint and activity times are normalized to UTC (issue #588)."""
        points = "".join(
            _tp(0, lat=10.0, lon=20.0, hr=150, stamp=f"2026-03-28T08:{minute:02d}:19-07:00") for minute in (19, 49)
        )
        document = _document(
            f'<Lap StartTime="2026-03-28T08:19:19-07:00"><TotalTimeSeconds>1800</TotalTimeSeconds><Track>{points}'
            "</Track></Lap>",
            activity_id="2026-03-28T08:19:19-07:00",
        )

        (payload,) = _assemble(tmp_path, document, timezone="America/Vancouver")

        assert payload["activity"].start_time == datetime(2026, 3, 28, 15, 19, 19, tzinfo=UTC)
        assert payload["activity"].end_time == datetime(2026, 3, 28, 15, 49, 19, tzinfo=UTC)
        assert payload["lat_lon_waypoints"][0]["time"] == "2026-03-28T15:19:19"
        assert payload["hr_waypoints"][0]["time"] == "2026-03-28T15:19:19"

    def test_start_comes_from_the_activity_id_not_the_first_positioned_point(self, tmp_path: Path) -> None:
        """A file whose first trackpoints lack a position still starts at the Activity Id time."""
        points = _tp(0) + "".join(_tp(60 * minute, lat=40.0 + minute / 200, lon=-3.0) for minute in range(1, 4))

        payload = _one(tmp_path, points, seconds=None)

        assert payload["activity"].start_time == _T0
        assert payload["activity"].end_time == _T0 + timedelta(minutes=3)
        assert payload["is_lat_lon_set"] is True
        assert len(payload["lat_lon_waypoints"]) == 3

    def test_elapsed_falls_back_to_timer_when_no_moving_time(self, tmp_path: Path) -> None:
        """Two samples an hour apart have no moving time, so the timer is the elapsed time."""
        payload = _one(tmp_path, _tp(0, lat=40.0, lon=-3.0) + _tp(3600, lat=40.0, lon=-3.0), seconds=None)

        assert payload["activity"].total_elapsed_time == 3600
        assert payload["activity"].total_timer_time == 3600

    def test_several_activities_give_several_payloads(self, tmp_path: Path) -> None:
        run = _document(_lap(0, _tp(0, lat=40.0, lon=-3.0) + _tp(30, lat=40.001, lon=-3.0)))
        ride = _document(_lap(3600, _tp(3600, lat=41.0, lon=-3.0) + _tp(3630, lat=41.001, lon=-3.0)), sport="Biking")
        ride = ride.replace(_stamp(0), _stamp(3600), 1)
        both = run.replace("</Activities>", ride.split("<Activities>")[1].split("</Activities>")[0] + "</Activities>")

        run_payload, ride_payload = _assemble(tmp_path, both)

        assert ride_payload["activity"].start_time == _T0 + timedelta(hours=1)
        assert run_payload["activity"].start_time == _T0
        assert run_payload["activity"].activity_type != ride_payload["activity"].activity_type


class TestHeartRate:
    """Heart-rate stream and summary."""

    def test_no_heart_rate_stream_without_heart_rate(self, tmp_path: Path) -> None:
        """A file recorded without a heart-rate sensor yields no heart-rate samples."""
        points = "".join(_tp(10 * i, lat=38.7 + i * 0.0002, lon=-9.1, ele=10.0) for i in range(3))

        payload = _one(tmp_path, points)

        assert payload["hr_waypoints"] == []
        assert payload["is_heart_rate_set"] is False
        assert len(payload["lat_lon_waypoints"]) == 3

    def test_summary_and_stream_leave_out_the_zero_dropouts(self, tmp_path: Path) -> None:
        """The HR summary and the stream are built from the samples without sensor-off zeros."""
        points = "".join(_tp(10 * i, hr=hr, lat=40.0 + 0.0001 * i, lon=-3.0) for i, hr in enumerate((0, 150, 160, 160)))

        payload = _one(tmp_path, points)

        activity = payload["activity"]
        # Zeros excluded: mean([150, 160]) = 155, max = 160.
        assert activity.average_hr == 155
        assert activity.max_hr == 160
        assert [wp["hr"] for wp in payload["hr_waypoints"]] == [150, 160, 160]


class TestDistanceAndTimer:
    """Distance, timer, pace and speed of a TCX activity."""

    def test_distance_is_derived_from_the_gps_track_when_missing(self, tmp_path: Path) -> None:
        # ~0.01 deg of latitude is about 1.1 km, covered in 30 hops of 10 s.
        points = "".join(_tp(10 * i, lat=40.0 + 0.01 * i / 30, lon=-3.0) for i in range(31))

        activity = _one(tmp_path, points)["activity"]

        assert 1000 < activity.distance < 1200
        assert activity.pace > 0

    def test_reported_distance_wins_over_the_gps_track(self, tmp_path: Path) -> None:
        points = "".join(_tp(10 * i, lat=40.0 + 0.01 * i / 30, lon=-3.0) for i in range(31))

        assert _one(tmp_path, points, distance=5000)["activity"].distance == 5000

    def test_pause_gap_splits_the_track_and_is_excluded_from_moving_time(self, tmp_path: Path) -> None:
        """A pause splits the track: no distance or moving time across it, and a 0 speed placeholder after it."""
        points = (
            _tp(0, lat=40.0, lon=-3.0)
            + _tp(10, lat=40.001, lon=-3.0)
            + _tp(310, lat=40.01, lon=-3.0)  # 300 s pause
            + _tp(320, lat=40.011, lon=-3.0)
        )

        payload = _one(tmp_path, points, seconds=None)

        activity = payload["activity"]
        assert activity.total_timer_time == 20
        assert len(payload["lat_lon_waypoints"]) == 4
        # Two hops of ~111 m; the ~1 km hop across the pause is not counted.
        assert 200 < activity.distance < 240
        assert payload["vel_waypoints"][2]["vel"] == 0
        assert [wp["pace"] for wp in payload["pace_waypoints"]] == pytest.approx([10 / 111.2, 10 / 111.2], rel=0.01)

    def test_sparse_track_is_one_segment_and_all_moving_time(self, tmp_path: Path) -> None:
        """A track sampled every 30 s is one run, all of it moving time."""
        points = "".join(_tp(30 * i, lat=40.0 + 0.001 * i, lon=-3.0) for i in range(5))

        payload = _one(tmp_path, points, seconds=None)

        assert payload["activity"].total_timer_time == 120
        assert 400 < payload["activity"].distance < 500
        assert all(wp["vel"] > 0 for wp in payload["vel_waypoints"][1:])

    def test_sparse_track_without_summary_distance(self, tmp_path: Path) -> None:
        """A 30 s sampled TCX without DistanceMeters gets a non-zero distance and pace."""
        points = "".join(_tp(30 * i, lat=40.0 + 0.001 * i, lon=-3.0) for i in range(5))

        activity = _one(tmp_path, points, seconds=120)["activity"]

        # 4 hops of 0.001 deg latitude, about 111 m each.
        assert 400 < activity.distance < 500
        assert activity.total_timer_time == 120
        assert activity.pace > 0
        assert activity.average_speed == pytest.approx(1 / activity.pace)

    def test_timer_and_pace_come_from_the_device_timer_and_elapsed_stays_wall_clock(self, tmp_path: Path) -> None:
        moving = "".join(_tp(10 * i, lat=40.0 + 0.0001 * i, lon=-3.0) for i in range(121))
        points = moving + _tp(3600, lat=40.02, lon=-3.0)

        activity = _one(tmp_path, points, seconds=1200, distance=5000)["activity"]

        assert activity.total_elapsed_time == 3600
        assert activity.total_timer_time == 1200
        assert activity.pace == 1200 / 5000

    def test_distance_from_the_track_skips_the_pause_gap(self, tmp_path: Path) -> None:
        moving = "".join(_tp(10 * i, lat=40.0 + 0.005 * i / 6, lon=-3.0) for i in range(7))
        # A single fix after a ten-minute pause, ~0.55 km further on, forms no run of its own.
        points = moving + _tp(600, lat=40.01, lon=-3.0)

        # ~0.005 deg of latitude is about 555 m; the ~555 m pause hop is excluded.
        assert 500 < _one(tmp_path, points)["activity"].distance < 600

    def test_points_that_every_pause_separates_have_no_distance(self, tmp_path: Path) -> None:
        """No run of two points means no distance, so no pace, average speed or maximum speed."""
        points = "".join(_tp(20 * i, lat=40.0 + 0.01 * i, lon=-3.0) for i in range(3))

        activity = _one(tmp_path, points)["activity"]

        assert activity.distance == 0
        assert activity.pace is None
        assert activity.average_speed is None
        assert activity.max_speed is None

    def test_a_stop_at_a_light_with_trackpoints_running_is_not_moving_time(self, tmp_path: Path) -> None:
        degrees = 5.0 / 111_195.0  # 5 m/s along a meridian
        lats = [40.0 + degrees * min(i, 100) for i in range(101)]
        lats += [lats[-1]] * 120 + [lats[-1] + degrees * (i + 1) for i in range(100)]
        points = "".join(_tp(i, lat=lat, lon=-3.0) for i, lat in enumerate(lats))

        activity = _one(tmp_path, points, seconds=None)["activity"]

        assert activity.total_elapsed_time == 320
        assert activity.total_timer_time == pytest.approx(200.0, abs=1.0)

    def test_a_one_second_spike_in_device_speed_raises_the_maximum_to_the_window_mean(self, tmp_path: Path) -> None:
        speeds = [5.0] * 61
        speeds[30] = 15.0
        points = "".join(_tp(i, speed=speed) for i, speed in enumerate(speeds))

        activity = _one(tmp_path, points, distance=300, sport="Biking")["activity"]

        assert activity.max_speed == pytest.approx(7.0)

    def test_max_speed_is_the_robust_maximum_of_the_derived_speed(self, tmp_path: Path) -> None:
        points = "".join(_tp(10 * i, lat=40.0 + 0.0001 * i, lon=-3.0) for i in range(31))

        activity = _one(tmp_path, points)["activity"]

        assert activity.max_speed == pytest.approx(1.112, rel=0.02)

    def test_device_speed_is_the_speed_stream(self, tmp_path: Path) -> None:
        """TPX Speed is used when any sample has one; zeros stay in the speed stream, not in the pace stream."""
        points = "".join(_tp(10 * i, speed=speed) for i, speed in enumerate((0.0, 2.0, 4.0)))

        payload = _one(tmp_path, points, distance=50)

        assert [wp["vel"] for wp in payload["vel_waypoints"]] == [0.0, 2.0, 4.0]
        assert [wp["pace"] for wp in payload["pace_waypoints"]] == [0.5, 0.25]
        assert payload["activity"].max_speed == 4.0


class TestRunCadence:
    """A running TCX with cadence only in TPX RunCadence doubles it to steps per minute."""

    @staticmethod
    def _assemble(tmp_path: Path, cadences: tuple[int, ...]) -> assembly.ActivityFilePayload:
        points = "".join(
            _tp(10 * i, lat=40.0 + 0.0001 * i, lon=-3.0, run_cad=cadence) for i, cadence in enumerate(cadences)
        )
        return _one(tmp_path, points, seconds=30, distance=90)

    def test_cadence_is_doubled(self, tmp_path: Path) -> None:
        payload = self._assemble(tmp_path, (84, 86, 88, 90))

        activity = payload["activity"]
        # The last sample holds no time: mean([84, 86, 88]) = 86 rpm, max 90 rpm.
        assert activity.average_cad == 172
        assert activity.max_cad == 180
        assert [wp["cad"] for wp in payload["cad_waypoints"]] == [168, 172, 176, 180]
        assert payload["laps"][0]["avg_cadence"] == 172
        assert payload["laps"][0]["max_cadence"] == 180

    def test_cadence_is_doubled_whatever_its_value(self, tmp_path: Path) -> None:
        """RunCadence is per-leg by format, so a high value is doubled too."""
        activity = self._assemble(tmp_path, (120, 122, 124, 126))["activity"]

        assert activity.average_cad == 244
        assert activity.max_cad == 252

    def test_a_lap_with_cadence_samples_takes_its_cadence_from_them(self, tmp_path: Path) -> None:
        """Garmin writes the lap's highest cadence in <Cadence>, so a lap whose samples carry cadence uses them."""
        document = _document(
            _lap(0, _tp(0, cad=70) + _tp(10, cad=80) + _tp(20, cad=90), "<Cadence>95</Cadence>"), sport="Biking"
        )

        (payload,) = _assemble(tmp_path, document)

        lap = payload["laps"][0]
        assert lap["avg_cadence"] == 75
        assert lap["max_cadence"] == 90

    def test_a_lap_without_cadence_samples_takes_the_cadence_element_as_its_average(self, tmp_path: Path) -> None:
        document = _document(_lap(0, _tp(0) + _tp(10), "<Cadence>88</Cadence>"), sport="Biking")

        (payload,) = _assemble(tmp_path, document)

        assert payload["laps"][0]["avg_cadence"] == 88


def test_activity_without_a_sport_is_assembled_as_other(tmp_path: Path) -> None:
    document = _document(_lap(0, _tp(0) + _tp(10), "<TotalTimeSeconds>5</TotalTimeSeconds>")).replace(
        ' Sport="Running"', ""
    )

    (payload,) = _assemble(tmp_path, document)

    assert payload["activity"].start_time == _T0


class TestStreamsWithoutPositions:
    """A TCX without GPS coordinates (indoor, treadmill) imports with the samples it has."""

    def test_position_less_trackpoints_keep_their_samples(self, tmp_path: Path) -> None:
        points = _tp(0, hr=150, ele=100, cad=85, power=220) + _tp(10, hr=152, ele=101, cad=86, power=230)

        payload = _one(tmp_path, points, sport="Biking")

        assert payload["lat_lon_waypoints"] == []
        assert len(payload["hr_waypoints"]) == 2
        assert len(payload["ele_waypoints"]) == 2
        assert len(payload["cad_waypoints"]) == 2
        assert len(payload["power_waypoints"]) == 2

    def test_no_speed_stream_without_positions_and_without_device_speed(self, tmp_path: Path) -> None:
        payload = _one(tmp_path, _tp(0, hr=150) + _tp(10, hr=152))

        assert payload["is_velocity_set"] is False
        assert payload["vel_waypoints"] == []
        assert payload["pace_waypoints"] == []

    def test_mixed_positioned_and_position_less_trackpoints(self, tmp_path: Path) -> None:
        points = _tp(0, lat=40.0, lon=-3.0, hr=140) + _tp(10, hr=141) + _tp(20, lat=40.001, lon=-3.0, hr=142)

        payload = _one(tmp_path, points)

        assert len(payload["lat_lon_waypoints"]) == 2
        assert len(payload["hr_waypoints"]) == 3
        vel = [wp["vel"] for wp in payload["vel_waypoints"]]
        assert vel[0] == 0
        # 0.001 deg of latitude is ~111 m, covered over the 20 s since the last positioned point.
        assert vel[1] == pytest.approx(111.2 / 20, rel=0.01)
        assert len(vel) == 2

    def test_a_positioned_point_sharing_a_partial_points_time_is_the_baseline(self, tmp_path: Path) -> None:
        points = (
            _tp(0, lat=40.0, lon=-3.0)
            + _tp(10, lon=-3.0)
            + _tp(10, lat=40.001, lon=-3.0)
            + _tp(20, lat=40.0015, lon=-3.0)
        )

        payload = _one(tmp_path, points)

        # 0.0005 deg of latitude is ~55.6 m, covered in the 10 s since the point at 10 s.
        assert payload["vel_waypoints"][-1]["vel"] == pytest.approx(55.6 / 10, rel=0.01)

    def test_without_gps_the_default_timezone_is_used(self, tmp_path: Path) -> None:
        points = _tp(0, hr=120) + _tp(1800, hr=130) + _tp(3600, hr=140)

        payload = _one(tmp_path, points, timezone="Europe/Lisbon")

        assert payload["is_lat_lon_set"] is False
        assert payload["lat_lon_waypoints"] == []
        assert payload["is_heart_rate_set"] is True
        assert payload["activity"].timezone == "Europe/Lisbon"

    def test_timezone_comes_from_the_first_positioned_point(self, tmp_path: Path) -> None:
        points = _tp(0) + _tp(1800, lat=40.0, lon=-3.0) + _tp(3600, lat=40.01, lon=-3.0)

        assert _one(tmp_path, points)["activity"].timezone == "Europe/Madrid"

    def test_real_gps_less_file(self, tmp_path: Path) -> None:
        points = "".join(_tp(60 * minute, hr=120 + minute) for minute in range(3))

        payload = _one(tmp_path, points, timezone="Europe/Lisbon")

        activity = payload["activity"]
        assert activity.start_time == _T0
        assert activity.end_time == _T0 + timedelta(minutes=2)
        # The device lap timer, not the elapsed time.
        assert activity.total_timer_time == 180
        assert activity.timezone == "Europe/Lisbon"
        assert payload["is_lat_lon_set"] is False
        assert payload["is_heart_rate_set"] is True
        assert [wp["hr"] for wp in payload["hr_waypoints"]] == [120, 121, 122]
        assert payload["is_elevation_set"] is False
        assert payload["ele_waypoints"] == []

    def test_gps_less_file_without_a_lap_timer_has_moving_time(self, tmp_path: Path) -> None:
        points = "".join(_tp(60 * minute, hr=120 + minute) for minute in range(3))

        assert _one(tmp_path, points, seconds=None)["activity"].total_timer_time == 120

    def test_file_with_too_few_gps_fixes(self, tmp_path: Path) -> None:
        points = _tp(0, lat=40.0, lon=-3.0) + _tp(60) + _tp(120)

        payload = _one(tmp_path, points, timezone="Europe/Lisbon")

        assert payload["activity"].start_time == _T0
        assert payload["activity"].end_time == _T0 + timedelta(minutes=2)
        assert len(payload["lat_lon_waypoints"]) == 1


class TestElevation:
    """Activity-level elevation from the smoothed stream."""

    @staticmethod
    def _assemble(tmp_path: Path, elevations: list[float | None]) -> assembly.ActivityFilePayload:
        points = "".join(_tp(10 * i, lat=40.0 + 0.0001 * i, lon=-3.0, ele=ele) for i, ele in enumerate(elevations))
        return _one(tmp_path, points, sport="Biking")

    def test_activity_elevation_from_smoothed_stream(self, tmp_path: Path) -> None:
        payload = self._assemble(tmp_path, [100.0 + i for i in range(31)])

        activity = payload["activity"]
        steps = parser_utils.elevation_step_waypoints(payload["ele_waypoints"])
        expected_gain = sum(wp["gain"] for wp in steps)
        assert activity.elevation_gain == round(expected_gain) > 0
        assert activity.elevation_loss == 0

    def test_no_altitude_keeps_elevation_none(self, tmp_path: Path) -> None:
        activity = self._assemble(tmp_path, [None] * 31)["activity"]

        assert activity.elevation_gain is None
        assert activity.elevation_loss is None

    def test_flat_altitude_stores_zero(self, tmp_path: Path) -> None:
        activity = self._assemble(tmp_path, [100.0] * 31)["activity"]

        assert activity.elevation_gain == 0
        assert activity.elevation_loss == 0

    def test_trackpoints_without_altitude_are_skipped(self, tmp_path: Path) -> None:
        points = "".join(
            _tp(10 * i, lat=40.0 + i * 0.001, lon=-3.0, ele=None if i % 3 == 0 else 100.0 + i) for i in range(30)
        )

        payload = _one(tmp_path, points)

        assert len(payload["ele_waypoints"]) == 20
        assert all(wp["ele"] is not None for wp in payload["ele_waypoints"])
        assert payload["activity"].elevation_gain is not None


class TestLaps:
    """Lap rows built from the TCX laps and the samples inside them."""

    @staticmethod
    def _two_laps(tmp_path: Path, elevation) -> assembly.ActivityFilePayload:
        first = "".join(_tp(10 * i, lat=40.0, lon=-3.0, ele=elevation(i)) for i in range(16))
        second = "".join(_tp(10 * i, lat=40.0, lon=-3.0, ele=elevation(i)) for i in range(16, 31))
        document = _document(
            _lap(0, first, "<TotalTimeSeconds>150</TotalTimeSeconds>"),
            _lap(155, second, "<TotalTimeSeconds>145</TotalTimeSeconds>"),
            sport="Biking",
        )
        (payload,) = _assemble(tmp_path, document)
        return payload

    def test_lap_ascent_comes_from_the_smoothed_stream(self, tmp_path: Path) -> None:
        """A 1 Hz sawtooth altitude has a huge raw sum of climbs, but the gain over its 30 m trend is small."""
        document = _document(
            _lap(
                0,
                "".join(_tp(i, ele=100 + i * 0.1 + (5.0 if i % 2 else -5.0)) for i in range(301)),
                "<TotalTimeSeconds>300</TotalTimeSeconds>",
            ),
            sport="Biking",
        )

        (payload,) = _assemble(tmp_path, document)

        (lap,) = payload["laps"]
        assert lap["total_ascent"] == pytest.approx(30, abs=6)
        assert lap["total_descent"] == 0

    def test_lap_sums_match_activity_when_boundary_falls_between_samples(self, tmp_path: Path) -> None:
        """The climb between lap 1's last sample and lap 2's first sample is counted once, in lap 2."""
        payload = self._two_laps(tmp_path, lambda i: 100.0 + 10 * i)

        laps = payload["laps"]
        activity_gain = sum(wp["gain"] for wp in parser_utils.elevation_step_waypoints(payload["ele_waypoints"]))
        assert abs(laps[0]["total_ascent"] + laps[1]["total_ascent"] - activity_gain) <= 1

    def test_flat_altitude_stores_zero(self, tmp_path: Path) -> None:
        laps = self._two_laps(tmp_path, lambda i: 100.0)["laps"]

        assert laps[0]["total_ascent"] == 0
        assert laps[0]["total_descent"] == 0

    def test_no_altitude_keeps_none(self, tmp_path: Path) -> None:
        laps = self._two_laps(tmp_path, lambda i: None)["laps"]

        assert laps[0]["total_ascent"] is None
        assert laps[0]["total_descent"] is None

    def test_lap_timer_is_the_device_timer_and_elapsed_runs_to_the_last_sample(self, tmp_path: Path) -> None:
        """A pause is in the lap's elapsed time, not in its timer."""
        points = _tp(0, lat=40.0, lon=-3.0) + _tp(10, lat=40.0, lon=-3.0)
        points += _tp(310, lat=40.0, lon=-3.0) + _tp(320, lat=40.0, lon=-3.0)

        (lap,) = _one(tmp_path, points, seconds=20)["laps"]

        assert lap["total_elapsed_time"] == 320
        assert lap["total_timer_time"] == 20

    def test_lap_elapsed_is_the_time_to_the_next_lap(self, tmp_path: Path) -> None:
        document = _document(
            _lap(0, _tp(0) + _tp(20), "<TotalTimeSeconds>18</TotalTimeSeconds>"),
            _lap(30, _tp(30) + _tp(50), "<TotalTimeSeconds>19</TotalTimeSeconds>"),
        )

        (payload,) = _assemble(tmp_path, document)

        assert [lap["total_elapsed_time"] for lap in payload["laps"]] == [30, 20]
        assert [lap["total_timer_time"] for lap in payload["laps"]] == [18, 19]

    def test_lap_speed_is_derived_from_distance_over_timer(self, tmp_path: Path) -> None:
        """Without a device lap speed the lap's average speed is m/s and its pace s/m."""
        points = _tp(0) + _tp(2423)

        (lap,) = _one(tmp_path, points, seconds=2423, distance=6795.94)["laps"]

        assert lap["enhanced_avg_speed"] == pytest.approx(6795.94 / 2423)
        assert lap["enhanced_avg_pace"] == pytest.approx(2423 / 6795.94)

    def test_lap_without_trackpoints_has_no_positions(self, tmp_path: Path) -> None:
        document = _document(
            f'<Lap StartTime="{_stamp(0)}"><TotalTimeSeconds>60</TotalTimeSeconds></Lap>',
            _lap(60, _tp(90, lat=40.0, lon=-3.0) + _tp(120, lat=40.001, lon=-3.0)),
        )

        (payload,) = _assemble(tmp_path, document)

        first = payload["laps"][0]
        assert len(payload["laps"]) == 2
        assert first["start_position_lat"] is None
        assert first["start_position_long"] is None
        assert first["end_position_lat"] is None
        assert first["end_position_long"] is None

    def test_lap_with_position_less_trackpoints_has_no_positions(self, tmp_path: Path) -> None:
        (lap,) = _one(tmp_path, _tp(0, hr=120) + _tp(1800, hr=121), seconds=1800)["laps"]

        assert lap["start_position_lat"] is None
        assert lap["end_position_long"] is None

    def test_lap_is_filled_from_its_own_samples(self, tmp_path: Path) -> None:
        points = "".join(
            _tp(10 * i, lat=40.0 + 0.0001 * i, lon=-3.0, hr=hr, power=power, cad=cad)
            for i, (hr, power, cad) in enumerate(((0, 100, 70), (140, 200, 80), (160, 300, 90)))
        )

        (lap,) = _one(tmp_path, points, seconds=20, sport="Biking")["laps"]

        # The last sample holds no time; the zero heart rate is a dropout left out with its time.
        assert (lap["avg_heart_rate"], lap["max_heart_rate"]) == (140, 160)
        assert (lap["avg_power"], lap["max_power"]) == (150, 300)
        # Twenty seconds hold under the 30 s a normalized power needs.
        assert lap["normalized_power"] is None
        assert (lap["avg_cadence"], lap["max_cadence"]) == (75, 90)
        assert lap["start_position_lat"] == 40.0
        assert lap["end_position_lat"] == pytest.approx(40.0002)

    def test_a_lap_without_a_device_normalised_power_gets_coggans_from_its_samples(self, tmp_path: Path) -> None:
        watts = _on_off_watts(600)
        points = "".join(_tp(i, power=w) for i, w in enumerate(watts))

        (lap,) = _one(tmp_path, points, seconds=599, sport="Biking")["laps"]

        assert lap["normalized_power"] == round(_coggan_np(watts))

    def test_activity_normalised_power_is_coggans(self, tmp_path: Path) -> None:
        watts = _on_off_watts(600)
        points = "".join(_tp(i, power=w) for i, w in enumerate(watts))

        activity = _one(tmp_path, points, seconds=599, sport="Biking")["activity"]

        assert activity.normalized_power == round(_coggan_np(watts))

    def test_short_laps_are_kept(self, tmp_path: Path) -> None:
        document = _document(
            _lap(0, _tp(0) + _tp(10), "<TotalTimeSeconds>10</TotalTimeSeconds>"),
            _lap(20, _tp(20), "<TotalTimeSeconds>5</TotalTimeSeconds>"),
        )

        (payload,) = _assemble(tmp_path, document)

        assert len(payload["laps"]) == 2

    def test_lap_summary_is_the_device_value_over_the_samples(self, tmp_path: Path) -> None:
        body = (
            "<TotalTimeSeconds>20</TotalTimeSeconds><AverageHeartRateBpm><Value>111</Value></AverageHeartRateBpm>"
            "<Extensions><x:LX><x:AvgSpeed>3.5</x:AvgSpeed><x:AvgRunCadence>85</x:AvgRunCadence></x:LX></Extensions>"
        )
        points = _tp(0, hr=150, run_cad=80) + _tp(10, hr=160, run_cad=90)

        (payload,) = _assemble(tmp_path, _document(_lap(0, points, body)))

        (lap,) = payload["laps"]
        assert lap["avg_heart_rate"] == 111
        assert lap["enhanced_avg_speed"] == 3.5
        assert lap["avg_cadence"] == 170
        assert lap["max_cadence"] == 180
