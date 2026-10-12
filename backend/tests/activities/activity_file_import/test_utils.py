"""Tests for shared activity file import utilities."""

from datetime import UTC, datetime, timedelta

import activities.activity_file_import.utils as afi_utils


class TestComputeDistanceFromWaypoints:
    """Test suite for compute_distance_from_waypoints."""

    def test_sums_geodesic_over_track(self):
        """Distance is the geodesic sum between consecutive points, in metres."""
        # ~0.01 deg of latitude ≈ 1.1 km.
        points = [
            {"lat": 40.0, "lon": -3.0},
            {"lat": 40.01, "lon": -3.0},
        ]
        distance = afi_utils.compute_distance_from_waypoints(points)
        assert 1000 < distance < 1200

    def test_empty_or_single_point_is_zero(self):
        """Fewer than two points yields zero distance."""
        assert afi_utils.compute_distance_from_waypoints([]) == 0.0
        assert afi_utils.compute_distance_from_waypoints([{"lat": 40.0, "lon": -3.0}]) == 0.0

    def test_skips_segments_with_missing_coordinates(self):
        """Segments touching a point without lat/lon are skipped."""
        points = [
            {"lat": 40.0, "lon": -3.0},
            {"lat": None, "lon": None},
            {"lat": 40.01, "lon": -3.0},
        ]
        # Both segments touch the None point, so nothing is accumulated.
        assert afi_utils.compute_distance_from_waypoints(points) == 0.0


class TestComputeMovingTimeFromTimes:
    """Test suite for compute_moving_time_from_times."""

    def test_empty_and_single_timestamp_are_zero(self):
        """Fewer than two timestamps yields zero moving time."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        assert afi_utils.compute_moving_time_from_times([]) == 0.0
        assert afi_utils.compute_moving_time_from_times([t]) == 0.0

    def test_sums_deltas_and_excludes_pause_gaps(self):
        """Deltas above the pause threshold are excluded from moving time."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        times = [
            t,
            t + timedelta(seconds=10),
            t + timedelta(seconds=310),  # 300 s pause — excluded
            t + timedelta(seconds=320),
        ]
        assert afi_utils.compute_moving_time_from_times(times) == 20.0

    def test_delta_equal_to_threshold_counts_as_moving(self):
        """A delta exactly at the threshold is still moving time."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        threshold = afi_utils.PAUSE_DETECTION_THRESHOLD_SECONDS
        times = [t, t + timedelta(seconds=threshold)]
        assert afi_utils.compute_moving_time_from_times(times) == threshold

    def test_ignores_non_positive_deltas(self):
        """Duplicate or out-of-order timestamps contribute nothing."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        times = [
            t,
            t,  # zero delta
            t - timedelta(seconds=5),  # negative delta
            t + timedelta(seconds=5),  # 10 s from previous point
        ]
        assert afi_utils.compute_moving_time_from_times(times) == 10.0
