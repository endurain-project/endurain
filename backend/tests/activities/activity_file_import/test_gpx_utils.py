"""Tests for GPX activity file import utilities."""

from datetime import UTC, datetime, timedelta

import gpxpy
import pytest
from geopy.distance import geodesic

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.gpx_utils as gpx_utils
import modules.activities.computation as activities_computation


def _write_gpx(tmp_path, body: str) -> str:
    """
    Write GPX test content to a temporary file.

    Args:
        tmp_path: Pytest temporary path fixture.
        body: GPX XML content.

    Returns:
        Path to the written GPX file as a string.
    """
    path = tmp_path / "activity.gpx"
    path.write_text(body, encoding="utf-8")
    return str(path)


def _patch_parser_side_effects(monkeypatch) -> None:
    """
    Disable external services and database-dependent parser lookups.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None.
    """
    monkeypatch.setattr(
        gpx_utils.activity_file_import_parser_utils,
        "resolve_timezone_from_lat_lon",
        lambda _lat, _lon, fallback: fallback,
    )


_SERVER_TZ = "UTC"


class TestParseGpxFile:
    """Test suite for full GPX parser behavior."""

    def test_parse_gpx_file_does_not_bridge_track_segments(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test distance, speed, and laps do not bridge GPX segments.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Segmented run</name>
                <type>Run</type>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:00:10Z</time>
                  </trkpt>
                </trkseg>
                <trkseg>
                  <trkpt lat="10.0" lon="10.0">
                    <time>2025-01-01T00:00:20Z</time>
                  </trkpt>
                  <trkpt lat="10.0" lon="10.001">
                    <time>2025-01-01T00:00:30Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        expected_distance = (
            geodesic(
                (0.0, 0.0),
                (0.0, 0.001),
            ).meters
            + geodesic(
                (10.0, 10.0),
                (10.0, 10.001),
            ).meters
        )

        assert result["activity"].distance == round(expected_distance)
        assert result["vel_waypoints"][0]["vel"] == 0
        assert result["vel_waypoints"][2]["vel"] == 0
        assert result["activity"].max_speed < 20
        assert all(lap["total_distance"] < 1000 for lap in result["laps"])

    def test_parse_gpx_file_sums_distance_over_multiple_points_in_one_segment(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test distance accumulates over every hop in a single segment.

        Regression test for the refactor from an inline per-point geodesic
        accumulator to summing ``compute_distance_from_waypoints`` per
        segment: verifies a segment with more than two points still sums
        every consecutive hop, not just the first/last point pair.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Multi-point run</name>
                <type>Run</type>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:00:10Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.002">
                    <time>2025-01-01T00:00:20Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.004">
                    <time>2025-01-01T00:00:30Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        expected_distance = (
            geodesic((0.0, 0.0), (0.0, 0.001)).meters
            + geodesic((0.0, 0.001), (0.0, 0.002)).meters
            + geodesic((0.0, 0.002), (0.0, 0.004)).meters
        )

        assert result["activity"].distance == round(expected_distance)

    def test_parse_gpx_file_converts_offset_timestamps_to_utc(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Timestamps with a non-UTC offset are stored as UTC (issue #588)."""
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Offset run</name>
                <type>Run</type>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2026-03-28T08:19:19-07:00</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2026-03-28T08:19:29-07:00</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        # 08:19:19-07:00 == 15:19:19 UTC; the offset must be converted (not
        # silently dropped) and ActivityCore stores it as an aware-UTC datetime.
        assert result["activity"].start_time == datetime(2026, 3, 28, 15, 19, 19, tzinfo=UTC)
        assert result["activity"].end_time == datetime(2026, 3, 28, 15, 19, 29, tzinfo=UTC)
        assert result["lat_lon_waypoints"][0]["time"] == "2026-03-28T15:19:19"
        assert result["laps"][0]["start_time"] == "2026-03-28T15:19:19"

    def test_parse_gpx_file_rejects_no_valid_segments(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test GPX files need at least one segment with two timed points.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Single point</name>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        assert exc_info.value.status_code == 400
        assert "no valid segments" in exc_info.value.detail

    def test_parse_gpx_file_sanitizes_elevation_values(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test implausible elevation values are ignored but zero is kept.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Elevation cleanup</name>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <ele>0</ele>
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <ele>10000</ele>
                    <time>2025-01-01T00:00:10Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.002">
                    <ele>-10000</ele>
                    <time>2025-01-01T00:00:20Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.003">
                    <ele>12.5</ele>
                    <time>2025-01-01T00:00:30Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["ele_waypoints"] == [
            {
                "time": "2025-01-01T00:00:00",
                "ele": 0.0,
            },
            {
                "time": "2025-01-01T00:00:30",
                "ele": 12.5,
            },
        ]

    def test_parse_gpx_file_reads_track_level_calories(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test track-level calories extensions populate the activity.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest"
              xmlns:gpxtrkx="http://example.com/gpxtrkx">
              <trk>
                <name>Calories ride</name>
                <extensions>
                  <gpxtrkx:TrackStatsExtension>
                    <gpxtrkx:Calories>123.7</gpxtrkx:Calories>
                  </gpxtrkx:TrackStatsExtension>
                </extensions>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:00:10Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].calories == 123

    def test_parse_gpx_file_without_extensions_creates_no_hr_or_cadence_stream(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test a GPX file with no sensor extensions produces no HR/cadence data.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Sensor-free run</name>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:00:10Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["is_heart_rate_set"] is False
        assert result["hr_waypoints"] == []
        assert result["is_cadence_set"] is False
        assert result["cad_waypoints"] == []
        assert result["activity"].average_hr is None
        assert result["activity"].max_hr is None

    def test_parse_gpx_file_with_only_hr_data_omits_cadence_stream(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test HR-only extensions persist an HR stream and no cadence stream.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>HR only run</name>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                    <extensions>
                      <TrackPointExtension><hr>140</hr></TrackPointExtension>
                    </extensions>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:00:10Z</time>
                    <extensions>
                      <TrackPointExtension><hr>150</hr></TrackPointExtension>
                    </extensions>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["is_heart_rate_set"] is True
        assert len(result["hr_waypoints"]) == 2
        assert result["is_cadence_set"] is False
        assert result["cad_waypoints"] == []

    def test_parse_gpx_file_does_not_zero_fill_missing_cadence_samples(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test a cadence sample missing from one point is skipped, not zeroed.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Cadence gap ride</name>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                    <extensions>
                      <TrackPointExtension><cad>80</cad></TrackPointExtension>
                    </extensions>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:00:10Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.002">
                    <time>2025-01-01T00:00:20Z</time>
                    <extensions>
                      <TrackPointExtension><cad>90</cad></TrackPointExtension>
                    </extensions>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["is_cadence_set"] is True
        assert [wp["cad"] for wp in result["cad_waypoints"]] == [80, 90]
        assert result["activity"].average_cad == 85

    def test_parse_gpx_file_with_all_zero_hr_creates_no_hr_stream(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test HR extensions present but always zero do not persist a stream.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Dropout run</name>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                    <extensions>
                      <TrackPointExtension><hr>0</hr></TrackPointExtension>
                    </extensions>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:00:10Z</time>
                    <extensions>
                      <TrackPointExtension><hr>0</hr></TrackPointExtension>
                    </extensions>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["is_heart_rate_set"] is False
        assert result["activity"].average_hr is None
        assert result["activity"].max_hr is None


def _steady_run_gpx(n_points: int, spike_indexes: dict[int, float]) -> str:
    """Build a ~3 m/s eastbound GPX run with 1 s spacing.

    Args:
        n_points: Number of trackpoints.
        spike_indexes: Map of point index to extra longitude offset in degrees.

    Returns:
        GPX XML text.
    """
    step = 0.0000269  # ~3 m at the equator
    points = []
    for i in range(n_points):
        lon = i * step + spike_indexes.get(i, 0.0)
        points.append(f'<trkpt lat="0.0" lon="{lon:.7f}"><time>2025-01-01T00:00:{i:02d}Z</time></trkpt>')
    return f'<gpx version="1.1" creator="pytest"><trk><type>Run</type><trkseg>{"".join(points)}</trkseg></trk></gpx>'


class TestParseGpxMaxSpeed:
    """Test suite for max speed robustness against GPS glitches."""

    def test_single_gps_spike_does_not_set_max_speed(self, tmp_path, monkeypatch):
        _patch_parser_side_effects(monkeypatch)
        path = _write_gpx(tmp_path, _steady_run_gpx(30, {15: 0.00045}))  # one fix ~50 m ahead

        result = gpx_utils.parse_gpx_file(path, user_id=1, default_timezone=_SERVER_TZ)

        assert max(w["vel"] for w in result["vel_waypoints"]) > 40
        assert result["activity"].max_speed == pytest.approx(3, abs=0.5)

    def test_two_adjacent_spiked_fixes_are_ignored(self, tmp_path, monkeypatch):
        _patch_parser_side_effects(monkeypatch)
        path = _write_gpx(tmp_path, _steady_run_gpx(30, {15: 0.00045, 16: 0.00045}))

        result = gpx_utils.parse_gpx_file(path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].max_speed == pytest.approx(3, abs=0.5)

    def test_sustained_fast_stretch_is_reported(self, tmp_path, monkeypatch):
        _patch_parser_side_effects(monkeypatch)
        step = 0.0000269
        lons = [i * step for i in range(15)]
        for _ in range(4):  # 4 samples at ~9 m/s
            lons.append(lons[-1] + step * 3)
        for _ in range(15):
            lons.append(lons[-1] + step)
        points = "".join(
            f'<trkpt lat="0.0" lon="{lon:.7f}"><time>2025-01-01T00:00:{i:02d}Z</time></trkpt>'
            for i, lon in enumerate(lons)
        )
        path = _write_gpx(
            tmp_path,
            f'<gpx version="1.1" creator="pytest"><trk><type>Run</type><trkseg>{points}</trkseg></trk></gpx>',
        )

        result = gpx_utils.parse_gpx_file(path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].max_speed == pytest.approx(9, abs=1)

    def test_fewer_than_window_samples_use_plain_max(self, tmp_path, monkeypatch):
        _patch_parser_side_effects(monkeypatch)
        path = _write_gpx(tmp_path, _steady_run_gpx(4, {2: 0.00045}))

        result = gpx_utils.parse_gpx_file(path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].max_speed == max(w["vel"] for w in result["vel_waypoints"])
        assert result["activity"].max_speed > 40


class TestExtractExtensionData:
    """Test suite for GPX trackpoint extension extraction."""

    def test_extract_extension_data_reads_namespaced_nested_values(self):
        """
        Test Garmin-style namespaced extensions are parsed recursively.
        """
        gpx = gpxpy.parse(
            """
            <gpx version="1.1" creator="pytest"
              xmlns:gpxtpx="http://example.com/gpxtpx"
              xmlns:ns3="http://example.com/custom">
              <trk><trkseg><trkpt lat="0" lon="0">
                <time>2025-01-01T00:00:00Z</time>
                <extensions>
                  <gpxtpx:TrackPointExtension>
                    <gpxtpx:hr>150</gpxtpx:hr>
                    <gpxtpx:cad>82</gpxtpx:cad>
                    <ns3:wrapper>
                      <ns3:power>250</ns3:power>
                    </ns3:wrapper>
                  </gpxtpx:TrackPointExtension>
                </extensions>
              </trkpt></trkseg></trk>
            </gpx>
            """
        )

        point = gpx.tracks[0].segments[0].points[0]

        assert gpx_utils._extract_extension_data(point) == (150, 82, 250)

    def test_extract_extension_data_reads_unprefixed_values(self):
        """
        Test OpenTracks and Tissot-style extension values are parsed.
        """
        gpx = gpxpy.parse(
            """
            <gpx version="1.1" creator="pytest">
              <trk><trkseg><trkpt lat="0" lon="0">
                <time>2025-01-01T00:00:00Z</time>
                <extensions>
                  <TrackPointExtension>
                    <heartrate>145</heartrate>
                    <cad>77</cad>
                    <power>211</power>
                  </TrackPointExtension>
                </extensions>
              </trkpt></trkseg></trk>
            </gpx>
            """
        )

        point = gpx.tracks[0].segments[0].points[0]

        assert gpx_utils._extract_extension_data(point) == (145, 77, 211)

    def test_extract_extension_data_ignores_invalid_numbers(self):
        """
        Test malformed extension values do not fail parsing.
        """
        gpx = gpxpy.parse(
            """
            <gpx version="1.1" creator="pytest">
              <trk><trkseg><trkpt lat="0" lon="0">
                <time>2025-01-01T00:00:00Z</time>
                <extensions>
                  <TrackPointExtension>
                    <hr>not-a-number</hr>
                    <cad></cad>
                    <power>205.8</power>
                  </TrackPointExtension>
                </extensions>
              </trkpt></trkseg></trk>
            </gpx>
            """
        )

        point = gpx.tracks[0].segments[0].points[0]

        assert gpx_utils._extract_extension_data(point) == (0, 0, 205)

    def test_extract_extension_data_returns_none_when_extensions_absent(self):
        """
        Test a point with no extensions yields all-None values, not zeros.
        """
        gpx = gpxpy.parse(
            """
            <gpx version="1.1" creator="pytest">
              <trk><trkseg><trkpt lat="0" lon="0">
                <time>2025-01-01T00:00:00Z</time>
              </trkpt></trkseg></trk>
            </gpx>
            """
        )

        point = gpx.tracks[0].segments[0].points[0]

        assert gpx_utils._extract_extension_data(point) == (None, None, None)

    """Test suite for instant speed calculations."""

    def test_calculate_instant_speed_treats_subsecond_delta_as_one_second(self):
        """
        Test speed calculation divides by at least one second.
        """
        start = datetime(2025, 1, 1, 0, 0, 0)
        end = start + timedelta(milliseconds=500)
        expected_distance = geodesic(
            (0.0, 0.0),
            (0.0, 0.0001),
        ).meters

        speed = activities_computation.calculate_instant_speed(
            start,
            end,
            0.0,
            0.0001,
            0.0,
            0.0,
        )

        assert speed == pytest.approx(expected_distance)
