"""Tests for shared activity file import utilities."""

from datetime import datetime, timedelta

import activities.activity.utils as activities_utils
import activities.activity_file_import.utils as afi_utils


def _straight_track(num_points: int, ele_fn) -> tuple[list[dict], list[dict]]:
    """Build a straight northbound track, ~111 m and 10 s per point.

    Args:
        num_points: Number of trackpoints.
        ele_fn: Callable index -> elevation (or None to skip the point).

    Returns:
        Tuple of (lat_lon_waypoints, ele_waypoints).
    """
    start = datetime(2025, 1, 1, 8, 0, 0)
    lat_lon_waypoints: list[dict] = []
    ele_waypoints: list[dict] = []
    for i in range(num_points):
        timestamp = (start + timedelta(seconds=10 * i)).strftime("%Y-%m-%dT%H:%M:%S")
        lat_lon_waypoints.append({"time": timestamp, "lat": 40.0 + i * 0.001, "lon": -3.0})
        elevation = ele_fn(i)
        if elevation is not None:
            ele_waypoints.append({"time": timestamp, "ele": elevation})
    return lat_lon_waypoints, ele_waypoints


class TestGenerateActivityLapsElevation:
    """Lap elevation gain/loss behavior (issue #161)."""

    def test_flat_track_stores_zero_ascent_not_none(self):
        """A flat lap has 0 m ascent/descent, not a blank (None)."""
        lat_lon, ele = _straight_track(25, lambda _i: 100.0)
        laps = afi_utils.generate_activity_laps(lat_lon, ele, [], [], [], [])
        assert len(laps) >= 2
        assert all(lap["total_ascent"] == 0 for lap in laps)
        assert all(lap["total_descent"] == 0 for lap in laps)

    def test_lap_ascent_sums_match_activity_total(self):
        """Lap gains partition the activity-level smoothed gain (no boundary clipping)."""
        lat_lon, ele = _straight_track(
            40,
            lambda i: 100 + i * 1.0 + (2.0 if i % 2 else -2.0),
        )
        laps = afi_utils.generate_activity_laps(lat_lon, ele, [], [], [], [])
        activity_gain, activity_loss = activities_utils.compute_elevation_gain_and_loss(ele)
        lap_gain_sum = sum(lap["total_ascent"] or 0 for lap in laps)
        lap_loss_sum = sum(lap["total_descent"] or 0 for lap in laps)
        # Per-lap values are rounded ints; allow only rounding error.
        assert abs(lap_gain_sum - activity_gain) <= 0.5 * len(laps)
        assert abs(lap_loss_sum - activity_loss) <= 0.5 * len(laps)

    def test_no_elevation_stream_keeps_none(self):
        """Without elevation data laps keep total_ascent/total_descent as None."""
        lat_lon, _ = _straight_track(25, lambda _i: None)
        laps = afi_utils.generate_activity_laps(lat_lon, [], [], [], [], [])
        assert laps
        assert all(lap["total_ascent"] is None for lap in laps)
        assert all(lap["total_descent"] is None for lap in laps)


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
