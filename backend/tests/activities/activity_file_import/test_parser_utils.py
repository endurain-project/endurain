"""Tests for shared activity file import utilities."""

import itertools
from datetime import UTC, datetime, timedelta

import pytest

import modules.activities.activity_file_import.parser_utils as afi_utils
import modules.activities.computation as activities_computation


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
        threshold = activities_computation.PAUSE_DETECTION_THRESHOLD_SECONDS
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


class TestTimezoneFinderCache:
    """The TimezoneFinder is built once and reused (perf on the ingestion path)."""

    def test_returns_same_cached_instance(self):
        import core.timezone as core_timezone

        assert core_timezone._timezone_finder() is core_timezone._timezone_finder()

    def test_resolve_timezone_uses_cached_finder(self):
        # A known land coordinate resolves to its IANA zone through the cached finder.
        assert afi_utils.resolve_timezone_from_lat_lon(38.7, -9.1, "UTC") == "Europe/Lisbon"


class TestLapStreamWindows:
    """Per-lap stream windows match a full scan and parse each timestamp once."""

    @staticmethod
    def _times(seconds: list[int]) -> list[str]:
        start = datetime(2025, 1, 1, tzinfo=UTC)
        return [(start + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%S") for s in seconds]

    def test_a_sample_on_a_lap_boundary_belongs_to_the_earlier_lap_only(self):
        steps = [{"time": t, "ele": 1.0, "gain": 1.0, "loss": 0.5} for t in self._times([0, 10, 20, 30])]
        start, middle, end = self._times([0, 20, 30])

        assert afi_utils.sum_lap_elevation(steps, start, middle) == (2.0, 1.0)
        assert afi_utils.sum_lap_elevation(steps, middle, end) == (1.0, 0.5)

    def test_laps_that_follow_one_another_add_up_to_the_stream(self):
        seconds = [0, 3, 7, 10, 12, 20, 21, 30]
        steps = [{"time": t, "ele": 1.0, "gain": float(i), "loss": i / 2} for i, t in enumerate(self._times(seconds))]
        cuts = self._times([0, 5, 10, 15, 30])

        parts = [afi_utils.sum_lap_elevation(steps, a, b) for a, b in itertools.pairwise(cuts)]

        assert sum(part[0] for part in parts if part) == sum(wp["gain"] for wp in steps)

    def test_a_lap_without_samples_has_no_sum(self):
        steps = [{"time": t, "ele": 1.0, "gain": 1.0, "loss": 0.0} for t in self._times([0, 30])]
        start, end = self._times([10, 20])

        assert afi_utils.sum_lap_elevation(steps, start, end) is None

    def test_unordered_samples_are_summed_by_their_time(self):
        steps = [{"time": t, "ele": 1.0, "gain": 1.0, "loss": 0.0} for t in self._times([20, 0, 10, 30])]
        start, end = self._times([0, 20])

        assert afi_utils.sum_lap_elevation(steps, start, end) == (2.0, 0.0)


class TestElevationWaypoints:
    """The stored elevation stream and the per-sample counts behind the gain."""

    @staticmethod
    def _stream(seconds: list[int], values: list[float]) -> list[dict]:
        start = datetime(2025, 1, 1, tzinfo=UTC)
        return [
            {"time": (start + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%S"), "ele": v}
            for s, v in zip(seconds, values, strict=True)
        ]

    def test_smoothing_averages_by_time_and_keeps_the_other_keys(self):
        stream = self._stream(list(range(21)), [0.0 if s < 10 else 11.0 for s in range(21)])

        smoothed = afi_utils.smooth_elevation_waypoints(stream)

        assert [wp["time"] for wp in smoothed] == [wp["time"] for wp in stream]
        # At 1 Hz, 5 s to 15 s: five samples of 0 and six of 11.
        assert smoothed[10]["ele"] == pytest.approx(6.0)

    def test_no_samples_give_no_stream(self):
        assert afi_utils.smooth_elevation_waypoints([]) == []
        assert afi_utils.elevation_step_waypoints([]) == []

    def test_steps_carry_the_smoothed_elevation_and_the_counts_at_each_sample(self):
        stream = self._stream(list(range(0, 400, 20)), [100.0] * 10 + [110.0] * 10)

        steps = afi_utils.elevation_step_waypoints(stream)

        assert [wp["ele"] for wp in steps] == [wp["ele"] for wp in afi_utils.smooth_elevation_waypoints(stream)]
        # The smoothed 10 m step counts to within the 3 m hysteresis of its height.
        assert sum(wp["gain"] for wp in steps) == pytest.approx(10.0, abs=3.0)
        assert sum(wp["loss"] for wp in steps) == 0.0
