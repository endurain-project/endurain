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

    def test_parse_gpx_file_excludes_pause_gap_from_timer_and_distance(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test a within-segment pause is excluded from timer, distance and pace.

        Regression test for issue #571: a 300 s recording pause inside a
        single ``<trkseg>`` must not count as active time, and the
        straight-line hop across the gap must not count as distance.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Paused run</name>
                <type>Run</type>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:00:10Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.010">
                    <time>2025-01-01T00:05:10Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.011">
                    <time>2025-01-01T00:05:20Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        expected_distance = geodesic((0.0, 0.0), (0.0, 0.001)).meters + geodesic((0.0, 0.010), (0.0, 0.011)).meters

        activity = result["activity"]
        assert activity.distance == round(expected_distance)
        assert activity.total_elapsed_time == 320
        assert activity.total_timer_time == 20
        assert activity.pace == pytest.approx(20 / expected_distance, rel=0.01)
        # First point after the pause has no previous cursor -> speed 0.
        assert result["vel_waypoints"][2]["vel"] == 0
        # No lap spans the pause gap.
        assert all(lap["total_distance"] < 1000 for lap in result["laps"])

    def test_parse_gpx_file_sparse_track_is_not_split_into_pauses(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test a track sampled every 30 s keeps its distance, timer and pace.
        """
        _patch_parser_side_effects(monkeypatch)
        points = "".join(
            f'<trkpt lat="0.0" lon="{0.001 * i:.3f}">'
            f"<time>2025-01-01T00:{(30 * i) // 60:02d}:{(30 * i) % 60:02d}Z</time></trkpt>"
            for i in range(5)
        )
        gpx_path = _write_gpx(
            tmp_path,
            f'<gpx version="1.1" creator="pytest"><trk><name>Sparse run</name><type>Run</type>'
            f"<trkseg>{points}</trkseg></trk></gpx>",
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        expected_distance = 4 * geodesic((0.0, 0.0), (0.0, 0.001)).meters

        activity = result["activity"]
        assert activity.distance == round(expected_distance)
        assert activity.total_timer_time == 120
        assert activity.pace == pytest.approx(120 / expected_distance, rel=0.01)
        assert result["laps"]

    def test_parse_gpx_file_timer_excludes_inter_segment_gap(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test timer time excludes the gap between two ``<trkseg>`` blocks.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Split run</name>
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
                  <trkpt lat="0.0" lon="0.010">
                    <time>2025-01-01T00:10:10Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.011">
                    <time>2025-01-01T00:10:20Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        activity = result["activity"]
        assert activity.total_elapsed_time == 620
        assert activity.total_timer_time == 20

    def test_parse_gpx_file_gap_equal_to_threshold_counts_as_moving(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test a delta exactly at the pause threshold stays active time.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Slow cadence run</name>
                <type>Run</type>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:00:15Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.002">
                    <time>2025-01-01T00:00:30Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        expected_distance = geodesic((0.0, 0.0), (0.0, 0.001)).meters + geodesic((0.0, 0.001), (0.0, 0.002)).meters

        activity = result["activity"]
        assert activity.distance == round(expected_distance)
        assert activity.total_timer_time == 30

    def test_parse_gpx_file_all_paused_falls_back_to_elapsed(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test a track whose only delta is a pause falls back to elapsed time.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>All paused</name>
                <type>Run</type>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:01:40Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        activity = result["activity"]
        assert activity.total_elapsed_time == 100
        assert activity.total_timer_time == 100
        assert activity.distance == 0
        assert activity.pace == 0

    def test_parse_gpx_file_ignores_duplicate_timestamps(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test duplicate timestamps do not inflate timer time or crash.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Duplicate stamps</name>
                <type>Run</type>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0">
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.001">
                    <time>2025-01-01T00:00:00Z</time>
                  </trkpt>
                  <trkpt lat="0.0" lon="0.002">
                    <time>2025-01-01T00:00:10Z</time>
                  </trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        activity = result["activity"]
        assert activity.total_elapsed_time == 10
        assert activity.total_timer_time == 10

    def test_parse_gpx_file_out_of_order_timestamp_does_not_inflate_timer(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test timestamps 0, 10, 5, 15 s give 15 s of timer time, not 20.
        """
        _patch_parser_side_effects(monkeypatch)
        gpx_path = _write_gpx(
            tmp_path,
            """
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Out of order</name>
                <type>Run</type>
                <trkseg>
                  <trkpt lat="0.0" lon="0.0"><time>2025-01-01T00:00:00Z</time></trkpt>
                  <trkpt lat="0.0" lon="0.001"><time>2025-01-01T00:00:10Z</time></trkpt>
                  <trkpt lat="0.0" lon="0.002"><time>2025-01-01T00:00:05Z</time></trkpt>
                  <trkpt lat="0.0" lon="0.003"><time>2025-01-01T00:00:15Z</time></trkpt>
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].total_timer_time == 15

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

    def test_parse_gpx_file_flat_track_stores_zero_elevation_gain(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test a flat track stores 0 m elevation gain/loss, not None.
        """
        _patch_parser_side_effects(monkeypatch)
        start = datetime(2025, 1, 1, 0, 0, 0)
        trkpts = "\n".join(
            f'<trkpt lat="{40.0 + i * 0.001}" lon="-3.0">'
            f"<ele>100.0</ele>"
            f"<time>{(start + timedelta(seconds=10 * i)).strftime('%Y-%m-%dT%H:%M:%SZ')}</time>"
            f"</trkpt>"
            for i in range(15)
        )
        gpx_path = _write_gpx(
            tmp_path,
            f"""
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Flat ride</name>
                <trkseg>
                {trkpts}
                </trkseg>
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].elevation_gain == 0
        assert result["activity"].elevation_loss == 0
        assert result["laps"]
        assert all(lap["total_ascent"] == 0 for lap in result["laps"])
        assert all(lap["total_descent"] == 0 for lap in result["laps"])

    def test_invalid_elevation_stream_stores_none(self):
        """
        Test an elevation stream with no valid values stores None, not 0 m.
        """
        start = datetime(2025, 1, 1, 0, 0, 0)
        state = gpx_utils.ParseState(
            timezone=_SERVER_TZ,
            activity_type="Ride",
            first_waypoint_time=start,
            last_waypoint_time=start + timedelta(minutes=1),
            ele_waypoints=[{"time": "2025-01-01T00:00:00", "ele": "n/a"}],
        )

        gpx_utils._compute_derived_metrics(state)
        activity = gpx_utils._build_activity_schema(state, user_id=1)

        assert activity.elevation_gain is None
        assert activity.elevation_loss is None

    def test_parse_gpx_file_smooths_elevation_once_for_all_segments(
        self,
        tmp_path,
        monkeypatch,
    ):
        """
        Test every segment's laps reuse one smoothed elevation stream.
        """
        _patch_parser_side_effects(monkeypatch)
        parser_utils = gpx_utils.activity_file_import_parser_utils
        generate_activity_laps = parser_utils.generate_activity_laps
        received_streams: list[list[dict] | None] = []

        def _record_laps(*args, **kwargs):
            received_streams.append(kwargs.get("smoothed_ele_waypoints"))
            return generate_activity_laps(*args, **kwargs)

        monkeypatch.setattr(parser_utils, "generate_activity_laps", _record_laps)
        start = datetime(2025, 1, 1, 0, 0, 0)
        segments = "\n".join(
            "<trkseg>"
            + "".join(
                f'<trkpt lat="{40.0 + (seg * 5 + i) * 0.001}" lon="-3.0">'
                f"<ele>{100.0 + seg * 5 + i}</ele>"
                f"<time>{(start + timedelta(seconds=10 * (seg * 5 + i))).strftime('%Y-%m-%dT%H:%M:%SZ')}</time>"
                f"</trkpt>"
                for i in range(5)
            )
            + "</trkseg>"
            for seg in range(3)
        )
        gpx_path = _write_gpx(
            tmp_path,
            f"""
            <gpx version="1.1" creator="pytest">
              <trk>
                <name>Segmented climb</name>
                {segments}
              </trk>
            </gpx>
            """.strip(),
        )

        result = gpx_utils.parse_gpx_file(gpx_path, user_id=1, default_timezone=_SERVER_TZ)

        assert len(received_streams) == 3
        assert all(stream is received_streams[0] for stream in received_streams)
        assert received_streams[0] == activities_computation.smooth_elevation_stream(result["ele_waypoints"])


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


def _segments_gpx(segments: list[list[tuple[float, str]]]) -> str:
    """Build a GPX file with one ``trkseg`` per entry.

    Args:
        segments: For each segment, ``(longitude, time-of-day)`` pairs on the equator.

    Returns:
        GPX XML text.
    """
    body = "".join(
        "<trkseg>"
        + "".join(f'<trkpt lat="0.0" lon="{lon:.7f}"><time>2025-01-01T{clock}Z</time></trkpt>' for lon, clock in seg)
        + "</trkseg>"
        for seg in segments
    )
    return f'<gpx version="1.1" creator="pytest"><trk><type>Run</type>{body}</trk></gpx>'


class TestParseGpxMaxSpeedSegmentPlaceholders:
    """The 0 placeholder at each segment start is not a measured speed."""

    _STEP = 0.0000269  # ~3 m at the equator

    def _short_segments(self) -> str:
        """Five 2-point segments at ~3 m/s, each followed by a lone point (a pause)."""
        segments = []
        for i in range(5):
            segments.append([(i * 0.001, f"00:{2 * i:02d}:00"), (i * 0.001 + self._STEP, f"00:{2 * i:02d}:01")])
            segments.append([(i * 0.001 + 0.0005, f"00:{2 * i + 1:02d}:00")])
        return _segments_gpx(segments)

    def test_many_short_segments_report_the_measured_speed(self, tmp_path, monkeypatch):
        _patch_parser_side_effects(monkeypatch)
        path = _write_gpx(tmp_path, self._short_segments())

        result = gpx_utils.parse_gpx_file(path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].max_speed == pytest.approx(3, abs=0.5)

    def test_stored_stream_and_average_still_include_the_placeholders(self, tmp_path, monkeypatch):
        _patch_parser_side_effects(monkeypatch)
        path = _write_gpx(tmp_path, self._short_segments())

        result = gpx_utils.parse_gpx_file(path, user_id=1, default_timezone=_SERVER_TZ)

        vels = [w["vel"] for w in result["vel_waypoints"]]
        assert len(vels) == 15
        assert vels.count(0) == 10
        assert set(result["vel_waypoints"][0]) == {"time", "vel"}
        assert result["activity"].average_speed == pytest.approx(sum(vels) / len(vels))

    def test_a_lap_starting_at_a_segment_start_reports_the_measured_speed(self, tmp_path, monkeypatch):
        _patch_parser_side_effects(monkeypatch)
        path = _write_gpx(tmp_path, self._short_segments())

        result = gpx_utils.parse_gpx_file(path, user_id=1, default_timezone=_SERVER_TZ)

        assert len(result["laps"]) == 5
        assert all(lap["enhanced_max_speed"] == pytest.approx(3, abs=0.5) for lap in result["laps"])

    def test_non_advancing_clock_gives_zero_max_speed(self, tmp_path, monkeypatch):
        _patch_parser_side_effects(monkeypatch)
        path = _write_gpx(
            tmp_path,
            _segments_gpx(
                [
                    [(0.0, "00:00:00"), (self._STEP, "00:00:00"), (2 * self._STEP, "00:00:00")],
                    [(0.001, "00:01:00"), (0.001 + self._STEP, "00:01:00")],
                ]
            ),
        )

        result = gpx_utils.parse_gpx_file(path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].max_speed == 0

    def test_single_point_segments_do_not_raise(self, tmp_path, monkeypatch):
        _patch_parser_side_effects(monkeypatch)
        path = _write_gpx(
            tmp_path,
            _segments_gpx(
                [
                    [(0.0, "00:00:00")],
                    [(0.001, "00:01:00")],
                    [(0.002, "00:02:00"), (0.002 + self._STEP, "00:02:01")],
                ]
            ),
        )

        result = gpx_utils.parse_gpx_file(path, user_id=1, default_timezone=_SERVER_TZ)

        assert result["activity"].max_speed == pytest.approx(3, abs=0.5)


class TestGenerateLapsMeasuredSamples:
    def _laps(self, measured_vel_times):
        times = [f"2025-01-01T00:00:0{i}" for i in range(5)]
        lat_lon = [{"time": t, "lat": 0.0, "lon": i * 0.0001} for i, t in enumerate(times)]
        vel = [{"time": t, "vel": v} for t, v in zip(times, [0, 0, 0, 3, 3], strict=True)]
        return gpx_utils.activity_file_import_parser_utils.generate_activity_laps(
            lat_lon, [], [], [], [], vel, measured_vel_times=measured_vel_times
        )

    def test_unmeasured_samples_are_left_out_of_the_lap_max(self):
        laps = self._laps({"2025-01-01T00:00:03", "2025-01-01T00:00:04"})

        assert laps[0]["enhanced_max_speed"] == 3
        assert laps[0]["enhanced_avg_speed"] == pytest.approx(1.2)

    def test_without_measured_times_every_sample_counts(self):
        assert self._laps(None)[0]["enhanced_max_speed"] == 0
