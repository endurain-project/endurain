"""Tests for TCX activity file import utilities."""

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import activities.activity_file_import.utils_tcx as utils_tcx


def _privacy_settings() -> SimpleNamespace:
    """
    Build privacy settings for parser tests.

    Returns:
        Object with the attributes expected by privacy kwarg builder.
    """
    return SimpleNamespace(
        default_activity_visibility="public",
        hide_activity_start_time=False,
        hide_activity_location=False,
        hide_activity_map=False,
        hide_activity_hr=False,
        hide_activity_power=False,
        hide_activity_cadence=False,
        hide_activity_elevation=False,
        hide_activity_speed=False,
        hide_activity_pace=False,
        hide_activity_laps=False,
        hide_activity_workout_sets_steps=False,
        hide_activity_gear=False,
    )


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

        waypoints = utils_tcx._extract_waypoints(trackpoints, tcx_file)

        assert len(waypoints["lat_lon_waypoints"]) == 1
        assert len(waypoints["hr_waypoints"]) == 1
        assert len(waypoints["cad_waypoints"]) == 1
        assert len(waypoints["ele_waypoints"]) == 1
        assert len(waypoints["power_waypoints"]) == 1
        assert all(wp["time"] == "2026-04-01T10:00:00" for wp in waypoints["lat_lon_waypoints"])

    def test_build_activity_handles_missing_start_and_end_time(self):
        """Test activity schema accepts missing start/end timestamps."""
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

        activity = utils_tcx._build_activity(
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
            gear_id=None,
            user_privacy_settings=_privacy_settings(),
        )

        assert activity.start_time is None
        assert activity.end_time is None
        assert activity.total_elapsed_time is None
        assert activity.total_timer_time is None

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

        waypoints = utils_tcx._extract_waypoints(trackpoints, tcx_file)

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

        activity = utils_tcx._build_activity(
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
            gear_id=None,
            user_privacy_settings=_privacy_settings(),
        )

        assert activity.start_time == "2026-03-28T15:19:19"
        assert activity.end_time == "2026-03-28T16:19:19"

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
                "activities.activity_file_import.utils_tcx._extract_waypoints",
                return_value=fake_waypoints,
            ),
            patch(
                "activities.activity_file_import.utils_tcx"
                ".user_default_gear_utils.get_user_default_gear_by_activity_type",
                return_value=None,
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx

            result = utils_tcx.parse_tcx_file(
                file="dummy.tcx",
                user_id=1,
                user_privacy_settings=_privacy_settings(),
                db=MagicMock(),
            )

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
                "activities.activity_file_import.utils_tcx._extract_waypoints",
                return_value=fake_waypoints,
            ),
            patch(
                "activities.activity_file_import.utils_tcx"
                ".user_default_gear_utils.get_user_default_gear_by_activity_type",
                return_value=None,
            ),
            patch(
                "activities.activity_file_import.utils_tcx.activity_file_import_utils.resolve_location",
                return_value=None,
            ),
            patch(
                "activities.activity_file_import.utils_tcx.activity_file_import_utils.resolve_timezone_from_lat_lon",
                return_value="UTC",
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx

            result = utils_tcx.parse_tcx_file(
                file="dummy.tcx",
                user_id=1,
                user_privacy_settings=_privacy_settings(),
                db=MagicMock(),
            )

        assert 1000 < result["activity"].distance < 1200
        assert result["activity"].pace > 0

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
                "activities.activity_file_import.utils_tcx._extract_waypoints",
                return_value=fake_waypoints,
            ),
            patch(
                "activities.activity_file_import.utils_tcx"
                ".user_default_gear_utils.get_user_default_gear_by_activity_type",
                return_value=None,
            ),
            patch(
                "activities.activity_file_import.utils_tcx.activity_file_import_utils.resolve_location",
                return_value=None,
            ),
            patch(
                "activities.activity_file_import.utils_tcx.activity_file_import_utils.resolve_timezone_from_lat_lon",
                return_value="UTC",
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx

            result = utils_tcx.parse_tcx_file(
                file="dummy.tcx",
                user_id=1,
                user_privacy_settings=_privacy_settings(),
                db=MagicMock(),
            )

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
    """Lap elevation gain/loss from the smoothed stream (issue #161)."""

    @staticmethod
    def _trackpoint(dt):
        return SimpleNamespace(latitude=40.0, longitude=-3.0, time=dt)

    def test_ignores_tcxreader_raw_ascent(self):
        """Lap ascent comes from the smoothed stream, not tcxreader's raw sum."""
        import activities.activity.utils as activities_utils

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
        smoothed = activities_utils.smooth_elevation_waypoints(ele_waypoints)
        lap = _make_lap(start, end, [self._trackpoint(start), self._trackpoint(end)], ascent=400.0, descent=380.0)
        tcx_file = SimpleNamespace(laps=[lap])

        laps = utils_tcx._parse_laps(tcx_file, smoothed)

        assert len(laps) == 1
        assert laps[0]["total_ascent"] is not None
        assert laps[0]["total_ascent"] < 100
        assert laps[0]["total_descent"] is not None
        assert laps[0]["total_descent"] < 100

    def test_flat_altitude_stores_zero(self):
        """A flat lap stores 0 m ascent/descent, not None."""
        import activities.activity.utils as activities_utils

        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        end = start + timedelta(seconds=300)
        ele_waypoints = [
            {
                "time": (start + timedelta(seconds=10 * i)).strftime("%Y-%m-%dT%H:%M:%S"),
                "ele": 100.0,
            }
            for i in range(31)
        ]
        smoothed = activities_utils.smooth_elevation_waypoints(ele_waypoints)
        lap = _make_lap(start, end, [self._trackpoint(start), self._trackpoint(end)])
        tcx_file = SimpleNamespace(laps=[lap])

        laps = utils_tcx._parse_laps(tcx_file, smoothed)

        assert laps[0]["total_ascent"] == 0
        assert laps[0]["total_descent"] == 0

    def test_no_altitude_keeps_none(self):
        """Without altitude data lap ascent/descent stay None."""
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        end = start + timedelta(seconds=300)
        lap = _make_lap(start, end, [self._trackpoint(start), self._trackpoint(end)])
        tcx_file = SimpleNamespace(laps=[lap])

        laps = utils_tcx._parse_laps(tcx_file, [])

        assert laps[0]["total_ascent"] is None
        assert laps[0]["total_descent"] is None


class TestParseTcxFileElevation:
    """Activity-level elevation from the smoothed stream (issue #161)."""

    @staticmethod
    def _run_parse(mock_tcx, fake_waypoints):
        with (
            patch("tcxreader.TCXReader") as mock_reader_class,
            patch(
                "activities.activity_file_import.utils_tcx._extract_waypoints",
                return_value=fake_waypoints,
            ),
            patch(
                "activities.activity_file_import.utils_tcx"
                ".user_default_gear_utils.get_user_default_gear_by_activity_type",
                return_value=None,
            ),
        ):
            mock_reader_class.return_value.read.return_value = mock_tcx
            return utils_tcx.parse_tcx_file(
                file="dummy.tcx",
                user_id=1,
                user_privacy_settings=_privacy_settings(),
                db=MagicMock(),
            )

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
        assert activity.elevation_gain is not None
        assert 20 <= activity.elevation_gain <= 30
        assert activity.elevation_loss == 0

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
