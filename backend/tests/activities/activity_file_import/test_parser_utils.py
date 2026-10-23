"""Tests for shared activity file import utilities."""

from datetime import UTC, datetime, timedelta

import modules.activities.activity_file_import.parser_utils as afi_utils
import modules.activities.computation as activities_computation


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
    """Lap elevation gain/loss from the once-smoothed stream."""

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
        activity_gain, activity_loss = activities_computation.compute_elevation_gain_and_loss(ele)
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
            t + timedelta(seconds=310),  # 300 s pause: excluded
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
            t + timedelta(seconds=5),  # 5 s from the latest timestamp, t
        ]
        assert afi_utils.compute_moving_time_from_times(times) == 5.0

    def test_out_of_order_timestamp_does_not_become_baseline(self):
        """Timestamps 0, 10, 5, 15 s give 15 s of moving time, not 20."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        times = [t + timedelta(seconds=s) for s in (0, 10, 5, 15)]
        assert afi_utils.compute_moving_time_from_times(times) == 15.0

    def test_sparse_track_sampling_is_not_a_pause(self):
        """A track sampled every 30 s counts every gap as moving time."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        times = [t + timedelta(seconds=30 * i) for i in range(5)]
        assert afi_utils.compute_moving_time_from_times(times) == 120.0


class TestPauseThresholdSeconds:
    """Test suite for pause_threshold_seconds."""

    def test_dense_track_uses_the_minimum(self):
        """1 s sampling keeps the minimum threshold."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        times = [t + timedelta(seconds=i) for i in range(10)]
        assert afi_utils.pause_threshold_seconds(times) == afi_utils.PAUSE_DETECTION_THRESHOLD_SECONDS

    def test_sparse_track_scales_with_the_median_interval(self):
        """30 s sampling raises the threshold to three intervals."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        times = [t + timedelta(seconds=30 * i) for i in range(10)]
        assert afi_utils.pause_threshold_seconds(times) == 90.0

    def test_long_pauses_do_not_move_the_median(self):
        """Two 600 s pauses in a 1 s track keep the minimum threshold."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        offsets = [*range(10), 610, 611, 612, 1212, 1213, 1214]
        times = [t + timedelta(seconds=s) for s in offsets]
        assert afi_utils.pause_threshold_seconds(times) == afi_utils.PAUSE_DETECTION_THRESHOLD_SECONDS

    def test_no_positive_gap_uses_the_minimum(self):
        """Empty, single or duplicate timestamps fall back to the minimum."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        assert afi_utils.pause_threshold_seconds([]) == afi_utils.PAUSE_DETECTION_THRESHOLD_SECONDS
        assert afi_utils.pause_threshold_seconds([t, t]) == afi_utils.PAUSE_DETECTION_THRESHOLD_SECONDS

    def test_too_few_gaps_use_the_minimum(self):
        """A single 300 s gap is a pause, not a sampling interval."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        times = [t, t + timedelta(seconds=300)]
        assert afi_utils.pause_threshold_seconds(times) == afi_utils.PAUSE_DETECTION_THRESHOLD_SECONDS


class TestTimezoneFinderCache:
    """The TimezoneFinder is built once and reused (perf on the ingestion path)."""

    def test_returns_same_cached_instance(self):
        import core.timezone as core_timezone

        assert core_timezone._timezone_finder() is core_timezone._timezone_finder()

    def test_resolve_timezone_uses_cached_finder(self):
        # A known land coordinate resolves to its IANA zone through the cached finder.
        assert afi_utils.resolve_timezone_from_lat_lon(38.7, -9.1, "UTC") == "Europe/Lisbon"
