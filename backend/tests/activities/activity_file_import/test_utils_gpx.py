"""Tests for GPX activity file import utilities."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import gpxpy
import pytest
from geopy.distance import geodesic

import activities.activity.utils as activities_utils
import activities.activity_file_import.utils_gpx as utils_gpx


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
        utils_gpx.activity_file_import_utils,
        "resolve_location",
        lambda _lat, _lon: None,
    )
    monkeypatch.setattr(
        utils_gpx.activity_file_import_utils,
        "resolve_timezone_from_lat_lon",
        lambda _lat, _lon, fallback: fallback,
    )
    monkeypatch.setattr(
        utils_gpx.user_default_gear_utils,
        "get_user_default_gear_by_activity_type",
        lambda _user_id, _activity_type, _db: None,
    )


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

        result = utils_gpx.parse_gpx_file(
            gpx_path,
            user_id=1,
            user_privacy_settings=_privacy_settings(),
            db=MagicMock(),
        )

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

        result = utils_gpx.parse_gpx_file(
            gpx_path,
            user_id=1,
            user_privacy_settings=_privacy_settings(),
            db=MagicMock(),
        )

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

        result = utils_gpx.parse_gpx_file(
            gpx_path,
            user_id=1,
            user_privacy_settings=_privacy_settings(),
            db=MagicMock(),
        )

        # 08:19:19-07:00 == 15:19:19 UTC; the offset must be
        # converted, not silently dropped.
        assert result["activity"].start_time == "2026-03-28T15:19:19"
        assert result["activity"].end_time == "2026-03-28T15:19:29"
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

        with pytest.raises(utils_gpx.HTTPException) as exc_info:
            utils_gpx.parse_gpx_file(
                gpx_path,
                user_id=1,
                user_privacy_settings=_privacy_settings(),
                db=MagicMock(),
            )

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

        result = utils_gpx.parse_gpx_file(
            gpx_path,
            user_id=1,
            user_privacy_settings=_privacy_settings(),
            db=MagicMock(),
        )

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

        result = utils_gpx.parse_gpx_file(
            gpx_path,
            user_id=1,
            user_privacy_settings=_privacy_settings(),
            db=MagicMock(),
        )

        assert result["activity"].calories == 123


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

        assert utils_gpx._extract_extension_data(point) == (150, 82, 250)

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

        assert utils_gpx._extract_extension_data(point) == (145, 77, 211)

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

        assert utils_gpx._extract_extension_data(point) == (0, 0, 205)


class TestCalculateInstantSpeed:
    """Test suite for instant speed calculations."""

    def test_calculate_instant_speed_preserves_subsecond_precision(self):
        """
        Test speed calculation does not truncate fractional seconds.
        """
        start = datetime(2025, 1, 1, 0, 0, 0)
        end = start + timedelta(milliseconds=500)
        expected_distance = geodesic(
            (0.0, 0.0),
            (0.0, 0.0001),
        ).meters

        speed = activities_utils.calculate_instant_speed(
            start,
            end,
            0.0,
            0.0001,
            0.0,
            0.0,
        )

        assert speed == pytest.approx(expected_distance / 0.5)
