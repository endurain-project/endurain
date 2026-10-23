"""Tests for TCX activity file import utilities."""

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.tcx_utils as tcx_utils
import modules.activities.computation as activities_computation

_SERVER_TZ = "UTC"


class TestUtilsTcx:
    """Test suite for TCX parser helper functions."""

    def test_extract_waypoints_skips_entries_without_time(self):
        """Test waypoints ignore trackpoints that have no timestamp."""
        dt = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)

        trackpoints = [
            {
                "time": None,
                "latitude": 10.0,
                "longitude": 20.0,
                "hr_value": 150,
                "cadence": 85,
                "elevation": 100,
            },
            {
                "time": dt,
                "latitude": 10.001,
                "longitude": 20.001,
                "hr_value": 152,
                "cadence": 88,
                "elevation": 101,
            },
        ]

        tcx_file = SimpleNamespace(
            trackpoints=[
                SimpleNamespace(
                    time=None,
                    tpx_ext={"Watts": 220, "RunCadence": 90},
                ),
                SimpleNamespace(
                    time=dt,
                    tpx_ext={"Watts": 230, "RunCadence": 92},
                ),
            ]
        )

        waypoints = tcx_utils._extract_waypoints(trackpoints, tcx_file)

        assert len(waypoints["lat_lon_waypoints"]) == 1
        assert len(waypoints["hr_waypoints"]) == 1
        assert len(waypoints["cad_waypoints"]) == 1
        assert len(waypoints["ele_waypoints"]) == 1
        assert len(waypoints["power_waypoints"]) == 1
        assert all(wp["time"] == "2026-04-01T10:00:00" for wp in waypoints["lat_lon_waypoints"])

    def test_build_activity_rejects_missing_start_and_end_time(self):
        """A TCX with no start/end is rejected with a named domain error."""
        tcx_file = SimpleNamespace(
            start_time=None,
            end_time=None,
            ascent=None,
            descent=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
        )

        with pytest.raises(core_exceptions.InvalidInputError, match="no activity start or end time"):
            tcx_utils._build_activity(
                tcx_file=tcx_file,
                user_id=1,
                activity_name="Indoor Session",
                activity_type=1,
                distance=0,
                timezone="UTC",
                pace=None,
                city=None,
                town=None,
                country=None,
                avg_power=None,
                max_power=None,
                norm_power=None,
            )

    def test_extract_waypoints_converts_offset_to_utc(self):
        """Offset-bearing trackpoint times are normalized to UTC (issue #588)."""
        # 08:19:19-07:00 is 15:19:19 UTC.
        dt = datetime(2026, 3, 28, 8, 19, 19, tzinfo=timezone(timedelta(hours=-7)))

        trackpoints = [
            {
                "time": dt,
                "latitude": 10.0,
                "longitude": 20.0,
                "hr_value": 150,
                "cadence": 85,
                "elevation": 100,
            },
        ]
        tcx_file = SimpleNamespace(trackpoints=[])

        waypoints = tcx_utils._extract_waypoints(trackpoints, tcx_file)

        assert waypoints["lat_lon_waypoints"][0]["time"] == "2026-03-28T15:19:19"
        assert waypoints["hr_waypoints"][0]["time"] == "2026-03-28T15:19:19"

    def test_build_activity_converts_offset_start_end_to_utc(self):
        """Activity start/end with offset are stored as UTC (issue #588)."""
        start = datetime(2026, 3, 28, 8, 19, 19, tzinfo=timezone(timedelta(hours=-7)))
        end = datetime(2026, 3, 28, 9, 19, 19, tzinfo=timezone(timedelta(hours=-7)))
        tcx_file = SimpleNamespace(
            start_time=start,
            end_time=end,
            ascent=None,
            descent=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
        )

        activity = tcx_utils._build_activity(
            tcx_file=tcx_file,
            user_id=1,
            activity_name="Ride",
            activity_type=1,
            distance=0,
            timezone="America/Vancouver",
            pace=None,
            city=None,
            town=None,
            country=None,
            avg_power=None,
            max_power=None,
            norm_power=None,
        )

        assert activity.start_time == datetime(2026, 3, 28, 15, 19, 19, tzinfo=UTC)
        assert activity.end_time == datetime(2026, 3, 28, 16, 19, 19, tzinfo=UTC)

    def test_parse_tcx_file_recomputes_hr_from_waypoints(self):
        """parse_tcx_file overwrites hr_avg/hr_max from hr_waypoints, dropping zeros."""
        dt_start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        dt_end = datetime(2026, 6, 20, 9, 0, 0, tzinfo=UTC)

        mock_tcx = SimpleNamespace(
            activity_type="Running",
            distance=5000.0,
            start_time=dt_start,
            end_time=dt_end,
            ascent=None,
            descent=None,
            hr_avg=103.0,  # stale — includes sensor-off zeros
            hr_max=160.0,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
            laps=[],
            trackpoints=[],
        )
        mock_tcx.trackpoints_to_dict = lambda: []

        fake_waypoints = {
            "lat_lon_waypoints": [],
            "lat_lon_segments": [],
            "hr_waypoints": [
                {"time": "2026-06-20T08:00:00", "hr": 0},
                {"time": "2026-06-20T08:00:10", "hr": 150},
                {"time": "2026-06-20T08:00:20", "hr": 160},
            ],
            "cad_waypoints": [],
            "ele_waypoints": [],
            "power_waypoints": [],
            "vel_waypoints": [],
            "pace_waypoints": [],
        }

        with (
            patch("tcxreader.TCXReader") as mock_reader_class,
            patch(
                "modules.activities.activity_file_import.tcx_utils._extract_waypoints",
                return_value=fake_waypoints,
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx

            result = tcx_utils.parse_tcx_file(file="dummy.tcx", user_id=1, default_timezone=_SERVER_TZ)

        activity = result["activity"]
        # Zeros excluded: mean([150, 160]) = 155, max = 160.
        assert activity.average_hr == 155
        assert activity.max_hr == 160

    def test_parse_tcx_file_derives_distance_from_gps_track_when_missing(self):
        """Missing tcx_file.distance falls back to the geodesic sum over the GPS track."""
        dt_start = datetime(2026, 6, 20, 8, 20, 3, tzinfo=UTC)
        dt_end = datetime(2026, 6, 20, 8, 25, 3, tzinfo=UTC)

        mock_tcx = SimpleNamespace(
            activity_type="Running",
            distance=None,
            start_time=dt_start,
            end_time=dt_end,
            ascent=None,
            descent=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
            laps=[],
            trackpoints=[],
        )
        trackpoints = [
            {"time": dt_start, "latitude": 40.0, "longitude": -3.0},
            {"time": dt_end, "latitude": 40.01, "longitude": -3.0},
        ]
        mock_tcx.trackpoints_to_dict = lambda: trackpoints

        fake_waypoints = {
            # ~0.01 deg of latitude ≈ 1.1 km.
            "lat_lon_waypoints": [
                {"time": "2026-06-20T08:20:03", "lat": 40.0, "lon": -3.0},
                {"time": "2026-06-20T08:25:03", "lat": 40.01, "lon": -3.0},
            ],
            "lat_lon_segments": [
                [
                    {"time": "2026-06-20T08:20:03", "lat": 40.0, "lon": -3.0},
                    {"time": "2026-06-20T08:25:03", "lat": 40.01, "lon": -3.0},
                ]
            ],
            "hr_waypoints": [],
            "cad_waypoints": [],
            "ele_waypoints": [],
            "power_waypoints": [],
            "vel_waypoints": [],
            "pace_waypoints": [],
        }

        with (
            patch("tcxreader.TCXReader") as mock_reader_class,
            patch(
                "modules.activities.activity_file_import.tcx_utils._extract_waypoints",
                return_value=fake_waypoints,
            ),
            patch(
                "modules.activities.activity_file_import.tcx_utils.activity_file_import_parser_utils.resolve_timezone_from_lat_lon",
                return_value="UTC",
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx

            result = tcx_utils.parse_tcx_file(file="dummy.tcx", user_id=1, default_timezone=_SERVER_TZ)

        assert 1000 < result["activity"].distance < 1200
        assert result["activity"].pace > 0

    def test_extract_waypoints_computes_moving_time_and_splits_segments_on_pause(self):
        """A pause gap splits the GPS track and is excluded from moving time."""
        t0 = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)

        trackpoints = [
            {"time": t0, "latitude": 40.0, "longitude": -3.0},
            {"time": t0 + timedelta(seconds=10), "latitude": 40.001, "longitude": -3.0},
            # 300 s pause.
            {"time": t0 + timedelta(seconds=310), "latitude": 40.01, "longitude": -3.0},
            {"time": t0 + timedelta(seconds=320), "latitude": 40.011, "longitude": -3.0},
        ]
        tcx_file = SimpleNamespace(trackpoints=[])

        waypoints = tcx_utils._extract_waypoints(trackpoints, tcx_file)

        assert waypoints["moving_time"] == 20.0
        assert len(waypoints["lat_lon_segments"]) == 2
        assert all(len(segment) == 2 for segment in waypoints["lat_lon_segments"])
        assert len(waypoints["lat_lon_waypoints"]) == 4
        # First point after the pause has no previous cursor -> speed 0.
        assert waypoints["vel_waypoints"][2]["vel"] == 0

    def test_extract_waypoints_keeps_a_sparse_track_in_one_segment(self):
        """A track sampled every 30 s is one segment, all of it moving time."""
        t0 = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
        trackpoints = [
            {"time": t0 + timedelta(seconds=30 * i), "latitude": 40.0 + 0.001 * i, "longitude": -3.0} for i in range(5)
        ]

        waypoints = tcx_utils._extract_waypoints(trackpoints, SimpleNamespace(trackpoints=[]))

        assert waypoints["moving_time"] == 120.0
        assert len(waypoints["lat_lon_segments"]) == 1
        assert len(waypoints["lat_lon_segments"][0]) == 5
        assert all(wp["vel"] > 0 for wp in waypoints["vel_waypoints"][1:])

    def test_parse_tcx_file_sparse_track_without_summary_distance(self, tmp_path):
        """A 30 s sampled TCX without DistanceMeters gets a non-zero distance and pace."""
        trackpoints = "".join(
            f"<Trackpoint><Time>2026-06-20T08:{(30 * i) // 60:02d}:{(30 * i) % 60:02d}Z</Time>"
            f"<Position><LatitudeDegrees>{40.0 + 0.001 * i:.3f}</LatitudeDegrees>"
            "<LongitudeDegrees>-3.0</LongitudeDegrees></Position></Trackpoint>"
            for i in range(5)
        )
        tcx_path = tmp_path / "sparse.tcx"
        tcx_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
            '<Activities><Activity Sport="Running"><Id>2026-06-20T08:00:00Z</Id>'
            '<Lap StartTime="2026-06-20T08:00:00Z"><TotalTimeSeconds>120</TotalTimeSeconds>'
            f"<Track>{trackpoints}</Track></Lap>"
            "</Activity></Activities></TrainingCenterDatabase>",
            encoding="utf-8",
        )

        with patch(
            "modules.activities.activity_file_import.tcx_utils.activity_file_import_parser_utils.resolve_timezone_from_lat_lon",
            return_value="UTC",
        ):
            result = tcx_utils.parse_tcx_file(file=str(tcx_path), user_id=1, default_timezone=_SERVER_TZ)

        activity = result["activity"]
        # 4 hops of 0.001 deg latitude, about 111 m each.
        assert 400 < activity.distance < 500
        assert activity.total_timer_time == 120
        assert activity.pace > 0

    def test_parse_tcx_file_uses_moving_time_for_timer_and_pace(self):
        """total_timer_time and pace come from moving time; elapsed stays wall-clock."""
        dt_start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        dt_end = datetime(2026, 6, 20, 9, 0, 0, tzinfo=UTC)

        mock_tcx = SimpleNamespace(
            activity_type="Running",
            distance=5000.0,
            start_time=dt_start,
            end_time=dt_end,
            ascent=None,
            descent=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
            laps=[],
            trackpoints=[],
        )
        trackpoints = [
            {"time": dt_start, "latitude": 40.0, "longitude": -3.0},
            {"time": dt_end, "latitude": 40.01, "longitude": -3.0},
        ]
        mock_tcx.trackpoints_to_dict = lambda: trackpoints

        fake_waypoints = {
            "lat_lon_waypoints": [
                {"time": "2026-06-20T08:00:00", "lat": 40.0, "lon": -3.0},
                {"time": "2026-06-20T09:00:00", "lat": 40.01, "lon": -3.0},
            ],
            "lat_lon_segments": [
                [
                    {"time": "2026-06-20T08:00:00", "lat": 40.0, "lon": -3.0},
                    {"time": "2026-06-20T09:00:00", "lat": 40.01, "lon": -3.0},
                ]
            ],
            "moving_time": 1200.0,
            "hr_waypoints": [],
            "cad_waypoints": [],
            "ele_waypoints": [],
            "power_waypoints": [],
            "vel_waypoints": [],
            "pace_waypoints": [],
        }

        with (
            patch("tcxreader.TCXReader") as mock_reader_class,
            patch(
                "modules.activities.activity_file_import.tcx_utils._extract_waypoints",
                return_value=fake_waypoints,
            ),
            patch(
                "modules.activities.activity_file_import.tcx_utils.activity_file_import_parser_utils.resolve_timezone_from_lat_lon",
                return_value="UTC",
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx

            result = tcx_utils.parse_tcx_file(file="dummy.tcx", user_id=1, default_timezone=_SERVER_TZ)

        activity = result["activity"]
        assert activity.total_elapsed_time == 3600
        assert activity.total_timer_time == 1200
        assert activity.pace == 1200 / 5000

    def test_parse_tcx_file_distance_fallback_skips_pause_gap(self):
        """The geodesic distance fallback sums pause-split segments only."""
        dt_start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        dt_end = datetime(2026, 6, 20, 8, 10, 0, tzinfo=UTC)

        mock_tcx = SimpleNamespace(
            activity_type="Running",
            distance=None,
            start_time=dt_start,
            end_time=dt_end,
            ascent=None,
            descent=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
            laps=[],
            trackpoints=[],
        )
        trackpoints = [
            {"time": dt_start, "latitude": 40.0, "longitude": -3.0},
            {"time": dt_end, "latitude": 40.01, "longitude": -3.0},
        ]
        mock_tcx.trackpoints_to_dict = lambda: trackpoints

        fake_waypoints = {
            # Flat stream contains the far post-pause point (~2.2 km away)...
            "lat_lon_waypoints": [
                {"time": "2026-06-20T08:00:00", "lat": 40.0, "lon": -3.0},
                {"time": "2026-06-20T08:00:10", "lat": 40.01, "lon": -3.0},
                {"time": "2026-06-20T08:10:00", "lat": 40.02, "lon": -3.0},
            ],
            # ...but pause-splitting isolated it, so only the first hop counts.
            "lat_lon_segments": [
                [
                    {"time": "2026-06-20T08:00:00", "lat": 40.0, "lon": -3.0},
                    {"time": "2026-06-20T08:00:10", "lat": 40.01, "lon": -3.0},
                ]
            ],
            "moving_time": 10.0,
            "hr_waypoints": [],
            "cad_waypoints": [],
            "ele_waypoints": [],
            "power_waypoints": [],
            "vel_waypoints": [],
            "pace_waypoints": [],
        }

        with (
            patch("tcxreader.TCXReader") as mock_reader_class,
            patch(
                "modules.activities.activity_file_import.tcx_utils._extract_waypoints",
                return_value=fake_waypoints,
            ),
            patch(
                "modules.activities.activity_file_import.tcx_utils.activity_file_import_parser_utils.resolve_timezone_from_lat_lon",
                return_value="UTC",
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx

            result = tcx_utils.parse_tcx_file(file="dummy.tcx", user_id=1, default_timezone=_SERVER_TZ)

        # ~0.01 deg of latitude ≈ 1.1 km; the ~1.1 km pause hop is excluded.
        assert 1000 < result["activity"].distance < 1200

    def test_parse_tcx_file_distance_fallback_is_zero_when_pause_leaves_no_segment(self):
        """Two GPS points split by a pause form no segment, so the fallback distance is 0."""
        dt_start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        dt_end = dt_start + timedelta(seconds=20)

        mock_tcx = SimpleNamespace(
            activity_type="Running",
            distance=None,
            start_time=dt_start,
            end_time=dt_end,
            ascent=None,
            descent=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
            laps=[],
            trackpoints=[],
        )
        trackpoints = [
            {"time": dt_start, "latitude": 40.0, "longitude": -3.0},
            {"time": dt_end, "latitude": 40.01, "longitude": -3.0},
        ]
        mock_tcx.trackpoints_to_dict = lambda: trackpoints

        with (
            patch("tcxreader.TCXReader") as mock_reader_class,
            patch(
                "modules.activities.activity_file_import.tcx_utils.activity_file_import_parser_utils.resolve_timezone_from_lat_lon",
                return_value="UTC",
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx

            result = tcx_utils.parse_tcx_file(file="dummy.tcx", user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].distance == 0

    def test_parse_laps_timer_time_excludes_pause(self):
        """Lap timer time sums moving deltas only; elapsed stays wall-clock."""
        t0 = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)

        def _tp(seconds: int) -> SimpleNamespace:
            return SimpleNamespace(
                time=t0 + timedelta(seconds=seconds),
                latitude=40.0,
                longitude=-3.0,
                tpx_ext={},
            )

        lap = SimpleNamespace(
            start_time=t0,
            end_time=t0 + timedelta(seconds=320),
            trackpoints=[_tp(0), _tp(10), _tp(310), _tp(320)],
            tpx_ext_stats={},
            distance=None,
            calories=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            ascent=None,
            descent=None,
            avg_speed=None,
        )
        tcx_file = SimpleNamespace(laps=[lap])

        laps = tcx_utils._parse_laps(tcx_file, [])

        assert laps[0]["total_elapsed_time"] == 320
        assert laps[0]["total_timer_time"] == 20

    def test_build_activity_falls_back_to_elapsed_without_timer(self):
        """Without a derived timer time, total_timer_time falls back to elapsed."""
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        end = datetime(2026, 6, 20, 9, 0, 0, tzinfo=UTC)
        tcx_file = SimpleNamespace(
            start_time=start,
            end_time=end,
            ascent=None,
            descent=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
        )

        activity = tcx_utils._build_activity(
            tcx_file=tcx_file,
            user_id=1,
            activity_name="Ride",
            activity_type=1,
            distance=0,
            timezone="UTC",
            pace=None,
            city=None,
            town=None,
            country=None,
            avg_power=None,
            max_power=None,
            norm_power=None,
        )

        assert activity.total_elapsed_time == 3600
        assert activity.total_timer_time == 3600

    def test_parse_tcx_file_keeps_reported_distance_when_present(self):
        """A real tcx_file.distance is used as-is, ignoring the GPS fallback."""
        dt_start = datetime(2026, 6, 20, 8, 20, 3, tzinfo=UTC)
        dt_end = datetime(2026, 6, 20, 8, 25, 3, tzinfo=UTC)

        mock_tcx = SimpleNamespace(
            activity_type="Running",
            distance=5000.0,
            start_time=dt_start,
            end_time=dt_end,
            ascent=None,
            descent=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
            laps=[],
            trackpoints=[],
        )
        trackpoints = [
            {"time": dt_start, "latitude": 40.0, "longitude": -3.0},
            {"time": dt_end, "latitude": 40.01, "longitude": -3.0},
        ]
        mock_tcx.trackpoints_to_dict = lambda: trackpoints

        fake_waypoints = {
            "lat_lon_waypoints": [
                {"time": "2026-06-20T08:20:03", "lat": 40.0, "lon": -3.0},
                {"time": "2026-06-20T08:25:03", "lat": 40.01, "lon": -3.0},
            ],
            "lat_lon_segments": [
                [
                    {"time": "2026-06-20T08:20:03", "lat": 40.0, "lon": -3.0},
                    {"time": "2026-06-20T08:25:03", "lat": 40.01, "lon": -3.0},
                ]
            ],
            "hr_waypoints": [],
            "cad_waypoints": [],
            "ele_waypoints": [],
            "power_waypoints": [],
            "vel_waypoints": [],
            "pace_waypoints": [],
        }

        with (
            patch("tcxreader.TCXReader") as mock_reader_class,
            patch(
                "modules.activities.activity_file_import.tcx_utils._extract_waypoints",
                return_value=fake_waypoints,
            ),
            patch(
                "modules.activities.activity_file_import.tcx_utils.activity_file_import_parser_utils.resolve_timezone_from_lat_lon",
                return_value="UTC",
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx

            result = tcx_utils.parse_tcx_file(file="dummy.tcx", user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].distance == 5000


def _make_lap(start, end, trackpoints, **overrides):
    """
    Build a fake tcxreader lap object.

    Args:
        start: Lap start datetime.
        end: Lap end datetime.
        trackpoints: Fake trackpoint namespaces.
        **overrides: Attribute overrides.

    Returns:
        SimpleNamespace mimicking a tcxreader lap.
    """
    defaults = dict(
        start_time=start,
        end_time=end,
        trackpoints=trackpoints,
        tpx_ext_stats={},
        distance=1000.0,
        calories=None,
        hr_avg=None,
        hr_max=None,
        cadence_avg=None,
        cadence_max=None,
        ascent=None,
        descent=None,
        avg_speed=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestParseLapsElevation:
    """Lap elevation gain/loss from the smoothed stream."""

    @staticmethod
    def _trackpoint(dt):
        return SimpleNamespace(latitude=40.0, longitude=-3.0, time=dt)

    def test_ignores_tcxreader_raw_ascent(self):
        """Lap ascent comes from the smoothed stream, not tcxreader's raw sum."""
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        end = start + timedelta(seconds=300)
        # Sawtooth: raw positive-delta sum is huge, smoothed gain is ~30 m.
        ele_waypoints = [
            {
                "time": (start + timedelta(seconds=10 * i)).strftime("%Y-%m-%dT%H:%M:%S"),
                "ele": 100 + i * 1.0 + (5.0 if i % 2 else -5.0),
            }
            for i in range(31)
        ]
        smoothed = activities_computation.smooth_elevation_stream(ele_waypoints)
        lap = _make_lap(start, end, [self._trackpoint(start), self._trackpoint(end)], ascent=400.0, descent=380.0)
        tcx_file = SimpleNamespace(laps=[lap])

        laps = tcx_utils._parse_laps(tcx_file, smoothed)

        assert len(laps) == 1
        assert laps[0]["total_ascent"] is not None
        assert laps[0]["total_ascent"] < 100
        assert laps[0]["total_descent"] is not None
        assert laps[0]["total_descent"] < 100

    def test_lap_sums_match_activity_when_boundary_falls_between_samples(self):
        """The climb between lap 1's last sample and lap 2's first sample is counted once, in lap 2."""
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        ele_waypoints = [
            {"time": (start + timedelta(seconds=10 * i)).strftime("%Y-%m-%dT%H:%M:%S"), "ele": 100.0 + 10 * i}
            for i in range(31)
        ]
        smoothed = activities_computation.smooth_elevation_stream(ele_waypoints)
        lap1_end = start + timedelta(seconds=150)
        lap2_start = start + timedelta(seconds=155)
        end = start + timedelta(seconds=300)
        tcx_file = SimpleNamespace(
            laps=[
                _make_lap(start, lap1_end, [self._trackpoint(start), self._trackpoint(lap1_end)]),
                _make_lap(lap2_start, end, [self._trackpoint(lap2_start), self._trackpoint(end)]),
            ]
        )

        laps = tcx_utils._parse_laps(tcx_file, smoothed)

        activity_gain, _ = activities_computation.sum_elevation_deltas(smoothed)
        assert abs(laps[0]["total_ascent"] + laps[1]["total_ascent"] - activity_gain) <= 1

    def test_flat_altitude_stores_zero(self):
        """A flat lap stores 0 m ascent/descent, not None."""
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        end = start + timedelta(seconds=300)
        ele_waypoints = [
            {
                "time": (start + timedelta(seconds=10 * i)).strftime("%Y-%m-%dT%H:%M:%S"),
                "ele": 100.0,
            }
            for i in range(31)
        ]
        smoothed = activities_computation.smooth_elevation_stream(ele_waypoints)
        lap = _make_lap(start, end, [self._trackpoint(start), self._trackpoint(end)])
        tcx_file = SimpleNamespace(laps=[lap])

        laps = tcx_utils._parse_laps(tcx_file, smoothed)

        assert laps[0]["total_ascent"] == 0
        assert laps[0]["total_descent"] == 0

    def test_no_altitude_keeps_none(self):
        """Without altitude data lap ascent/descent stay None."""
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        end = start + timedelta(seconds=300)
        lap = _make_lap(start, end, [self._trackpoint(start), self._trackpoint(end)])
        tcx_file = SimpleNamespace(laps=[lap])

        laps = tcx_utils._parse_laps(tcx_file, [])

        assert laps[0]["total_ascent"] is None
        assert laps[0]["total_descent"] is None


class TestParseTcxFileElevation:
    """Activity-level elevation from the smoothed stream."""

    @staticmethod
    def _run_parse(mock_tcx, fake_waypoints):
        with (
            patch("tcxreader.TCXReader") as mock_reader_class,
            patch(
                "modules.activities.activity_file_import.tcx_utils._extract_waypoints",
                return_value=fake_waypoints,
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx
            return tcx_utils.parse_tcx_file(file="dummy.tcx", user_id=1, default_timezone=_SERVER_TZ)

    @staticmethod
    def _mock_tcx(**overrides):
        defaults = dict(
            activity_type="Biking",
            distance=5000.0,
            start_time=datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 6, 20, 9, 0, 0, tzinfo=UTC),
            ascent=None,
            descent=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
            laps=[],
            trackpoints=[],
        )
        defaults.update(overrides)
        mock_tcx = SimpleNamespace(**defaults)
        mock_tcx.trackpoints_to_dict = lambda: []
        return mock_tcx

    @staticmethod
    def _fake_waypoints(ele_waypoints):
        return {
            "lat_lon_waypoints": [],
            "lat_lon_segments": [],
            "hr_waypoints": [],
            "cad_waypoints": [],
            "ele_waypoints": ele_waypoints,
            "power_waypoints": [],
            "vel_waypoints": [],
            "pace_waypoints": [],
        }

    def test_activity_elevation_from_smoothed_stream(self):
        """Activity gain uses the smoothed stream, ignoring tcx_file.ascent."""
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        ele_waypoints = [
            {
                "time": (start + timedelta(seconds=10 * i)).strftime("%Y-%m-%dT%H:%M:%S"),
                "ele": 100.0 + i,
            }
            for i in range(31)
        ]
        mock_tcx = self._mock_tcx(ascent=429.0, descent=441.0)

        result = self._run_parse(mock_tcx, self._fake_waypoints(ele_waypoints))

        activity = result["activity"]
        expected_gain, expected_loss = activities_computation.compute_elevation_gain_and_loss(ele_waypoints)
        assert activity.elevation_gain == round(expected_gain) > 0
        assert activity.elevation_loss == round(expected_loss) == 0

    def test_no_altitude_keeps_elevation_none(self):
        """Without altitude data elevation gain/loss stay None."""
        mock_tcx = self._mock_tcx()

        result = self._run_parse(mock_tcx, self._fake_waypoints([]))

        activity = result["activity"]
        assert activity.elevation_gain is None
        assert activity.elevation_loss is None

    def test_flat_altitude_stores_zero(self):
        """A flat altitude stream stores 0 m gain/loss, not None."""
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        ele_waypoints = [
            {
                "time": (start + timedelta(seconds=10 * i)).strftime("%Y-%m-%dT%H:%M:%S"),
                "ele": 100.0,
            }
            for i in range(31)
        ]
        mock_tcx = self._mock_tcx()

        result = self._run_parse(mock_tcx, self._fake_waypoints(ele_waypoints))

        activity = result["activity"]
        assert activity.elevation_gain == 0
        assert activity.elevation_loss == 0

    def test_trackpoints_without_altitude_are_skipped(self):
        """Trackpoints whose elevation is None stay out of the elevation stream."""
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        trackpoints = [
            {
                "time": start + timedelta(seconds=10 * i),
                "latitude": 40.0 + i * 0.001,
                "longitude": -3.0,
                "elevation": None if i % 3 == 0 else 100.0 + i,
            }
            for i in range(30)
        ]
        mock_tcx = self._mock_tcx(trackpoints=[SimpleNamespace(time=tp["time"], tpx_ext={}) for tp in trackpoints])
        mock_tcx.trackpoints_to_dict = lambda: trackpoints

        with (
            patch("tcxreader.TCXReader") as mock_reader_class,
            patch(
                "modules.activities.activity_file_import.tcx_utils.activity_file_import_parser_utils.resolve_timezone_from_lat_lon",
                return_value="UTC",
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx
            result = tcx_utils.parse_tcx_file(file="dummy.tcx", user_id=1, default_timezone=_SERVER_TZ)

        assert len(result["ele_waypoints"]) == 20
        assert all(wp["ele"] is not None for wp in result["ele_waypoints"])
        assert result["activity"].elevation_gain is not None
