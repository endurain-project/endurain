"""Tests for shared activity file import utilities."""

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
