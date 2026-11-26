"""Tests for shared activity file import utilities."""

import itertools
from datetime import UTC, datetime, timedelta

import pytest

import modules.activities.activity_file_import.parser_utils as afi_utils


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
