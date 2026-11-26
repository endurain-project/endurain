"""Tests for the published activity metric computations.

The stream maths moved out of the activities core, then out of the parser
package once the Strava adapter needed it too — it is a module-level surface now.
"""

import itertools
import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from geopy.distance import geodesic

import modules.activities.computation as activities_computation
from modules.activities.computation import (
    calculate_avg_and_max,
    calculate_instant_speed,
    calculate_np,
    calculate_pace,
    calculate_pace_from_duration,
    calculate_robust_max,
    compute_elevation_gain_and_loss,
    double_cadence_waypoints,
    double_running_cadence,
    normalized_power,
    smooth_elevation_stream,
    sum_elevation_deltas,
    time_weighted_mean,
)


class TestCalculateInstantSpeed:
    def test_returns_zero_when_prev_time_none(self):
        t = datetime(2024, 1, 15, 8, 0, 5)
        result = calculate_instant_speed(
            prev_time=None,
            waypoint_time=t,
            latitude=38.0,
            longitude=-9.0,
            prev_latitude=38.001,
            prev_longitude=-9.001,
        )
        assert result == 0

    def test_returns_zero_when_prev_coords_none(self):
        t = datetime(2024, 1, 15, 8, 0, 5)
        result = calculate_instant_speed(
            prev_time=datetime(2024, 1, 15, 8, 0, 0),
            waypoint_time=t,
            latitude=38.0,
            longitude=-9.0,
            prev_latitude=None,
            prev_longitude=None,
        )
        assert result == 0

    def test_returns_zero_when_time_delta_zero(self):
        t = datetime(2024, 1, 15, 8, 0, 0)
        result = calculate_instant_speed(
            prev_time=t,
            waypoint_time=t,
            latitude=38.0,
            longitude=-9.0,
            prev_latitude=38.001,
            prev_longitude=-9.001,
        )
        assert result == 0

    def test_returns_positive_speed(self):
        result = calculate_instant_speed(
            prev_time=datetime(2024, 1, 15, 8, 0, 0),
            waypoint_time=datetime(2024, 1, 15, 8, 1, 0),
            latitude=38.001,
            longitude=-9.001,
            prev_latitude=38.0,
            prev_longitude=-9.0,
        )
        assert result > 0

    def test_subsecond_delta_counts_as_one_second(self):
        start = datetime(2024, 1, 15, 8, 0, 0)
        distance = geodesic((0.0, 0.0), (0.0, 0.000135)).meters  # ~15 m
        result = calculate_instant_speed(
            prev_time=start,
            waypoint_time=start + timedelta(milliseconds=300),
            latitude=0.0,
            longitude=0.000135,
            prev_latitude=0.0,
            prev_longitude=0.0,
        )
        assert result == pytest.approx(distance)
        assert 14 < result < 16


class TestCalculateRobustMax:
    def test_empty_returns_zero(self):
        assert calculate_robust_max([]) == 0

    def test_fewer_than_window_returns_plain_max(self):
        assert calculate_robust_max([1.0, 9.0, 2.0, 3.0]) == 9.0

    def test_single_spike_is_ignored(self):
        assert calculate_robust_max([3.0] * 10 + [50.0] + [3.0] * 10) == 3.0

    def test_two_consecutive_spikes_are_ignored(self):
        assert calculate_robust_max([3.0] * 10 + [50.0, 48.0] + [3.0] * 10) == 3.0

    def test_sustained_fast_stretch_is_reported(self):
        assert calculate_robust_max([3.0] * 10 + [8.0, 8.0, 8.0] + [3.0] * 10) == 8.0

    def test_trailing_edge_is_not_clamped(self):
        assert calculate_robust_max([3.0] * 10 + [50.0]) == 3.0


class TestComputeElevationGainAndLoss:
    def test_returns_none_for_empty_list(self):
        assert compute_elevation_gain_and_loss([]) == (None, None)

    @pytest.mark.parametrize("waypoints", [[{"no_ele": 100}], [{"ele": "n/a"}], [{"ele": None}]])
    def test_returns_none_for_invalid_data(self, waypoints):
        assert compute_elevation_gain_and_loss(waypoints) == (None, None)

    def test_flat_elevation_returns_zero(self):
        result = compute_elevation_gain_and_loss([{"ele": 100}, {"ele": 100}, {"ele": 100}])
        assert result == (0.0, 0.0)

    def test_computes_gain(self):
        gain, loss = compute_elevation_gain_and_loss(
            [{"ele": 100}, {"ele": 110}, {"ele": 120}],
            median_window=1,
            avg_window=1,
            threshold=0.1,
        )
        assert gain == 20.0
        assert loss == 0.0

    def test_computes_loss(self):
        gain, loss = compute_elevation_gain_and_loss(
            [{"ele": 120}, {"ele": 110}, {"ele": 100}],
            median_window=1,
            avg_window=1,
            threshold=0.1,
        )
        assert gain == 0.0
        assert loss == 20.0

    def test_computes_gain_and_loss_with_threshold(self):
        gain, loss = compute_elevation_gain_and_loss(
            [{"ele": 100}, {"ele": 100.05}, {"ele": 120}, {"ele": 100}],
            median_window=1,
            avg_window=1,
            threshold=0.1,
        )
        assert gain > 0
        assert loss > 0

    def test_median_window_large_handles_small_list(self):
        gain, loss = compute_elevation_gain_and_loss([{"ele": 100}], median_window=10, avg_window=10, threshold=0.1)
        assert gain == 0.0
        assert loss == 0.0


class TestSumElevationDeltas:
    def test_flat_series_returns_zero_zero(self):
        assert sum_elevation_deltas([{"ele": 100.0}, {"ele": 100.0}, {"ele": 100.0}]) == (0.0, 0.0)

    def test_empty_returns_zero_zero(self):
        assert sum_elevation_deltas([]) == (0.0, 0.0)

    def test_composition_equals_compute_elevation_gain_and_loss(self):
        # Synthetic noisy climb: linear trend + sinusoid + alternating jitter.
        elevations = [{"ele": 100 + i * 0.5 + math.sin(i / 5) * 3 + (0.5 if i % 2 else -0.5)} for i in range(200)]
        expected = compute_elevation_gain_and_loss(elevations)
        assert sum_elevation_deltas(smooth_elevation_stream(elevations)) == expected


class TestCalculatePace:
    def test_returns_zero_when_distance_zero(self):
        t = datetime(2024, 1, 15, 8, 0, 0)
        result = calculate_pace(distance=0, first_waypoint_time=t, last_waypoint_time=t)
        assert result == 0

    def test_calculates_pace_correctly(self):
        result = calculate_pace(
            distance=10000,
            first_waypoint_time=datetime(2024, 1, 15, 8, 0, 0),
            last_waypoint_time=datetime(2024, 1, 15, 9, 0, 0),
        )
        assert result == 3600.0 / 10000

    def test_calculates_pace_with_fractional_distance(self):
        result = calculate_pace(
            distance=5000,
            first_waypoint_time=datetime(2024, 1, 15, 8, 0, 0),
            last_waypoint_time=datetime(2024, 1, 15, 8, 25, 0),
        )
        assert result == 1500.0 / 5000


class TestCalculatePaceFromDuration:
    def test_returns_zero_when_distance_zero(self):
        assert calculate_pace_from_duration(distance=0, duration_seconds=600) == 0

    def test_returns_zero_when_duration_non_positive(self):
        assert calculate_pace_from_duration(distance=5000, duration_seconds=0) == 0
        assert calculate_pace_from_duration(distance=5000, duration_seconds=-10) == 0

    def test_calculates_pace_correctly(self):
        result = calculate_pace_from_duration(distance=10000, duration_seconds=3600)
        assert result == 3600.0 / 10000

    def test_calculates_pace_with_fractional_duration(self):
        result = calculate_pace_from_duration(distance=5000, duration_seconds=1500)
        assert result == 1500.0 / 5000


class TestCalculateAvgAndMax:
    def test_returns_zero_for_empty_data(self):
        assert calculate_avg_and_max([], "hr") == (0.0, 0.0)

    def test_returns_zero_for_all_none_values(self):
        assert calculate_avg_and_max([{"hr": None}, {"hr": None}], "hr") == (0.0, 0.0)

    def test_returns_zero_for_missing_key(self):
        assert calculate_avg_and_max([{"other": 100}], "hr") == (0.0, 0.0)

    def test_computes_avg_and_max(self):
        avg, max_val = calculate_avg_and_max([{"hr": 140}, {"hr": 150}, {"hr": 160}], "hr")
        assert avg == 150.0
        assert max_val == 160.0

    def test_handles_mixed_none_and_values(self):
        avg, max_val = calculate_avg_and_max([{"hr": 140}, {"hr": None}, {"hr": 160}], "hr")
        assert avg == 150.0
        assert max_val == 160.0

    def test_single_value(self):
        avg, max_val = calculate_avg_and_max([{"hr": 145}], "hr")
        assert avg == 145.0
        assert max_val == 145.0

    def test_returns_zero_on_value_error(self):
        result = calculate_avg_and_max([{"hr": "not_a_number"}], "hr")
        assert result == (0.0, 0.0)

    def test_hr_zeros_are_excluded_from_avg_and_max(self):
        # Zero is a sensor-off sentinel; the filter must drop it so
        # only the real readings [150, 160] contribute.
        avg, max_val = calculate_avg_and_max(
            [{"hr": 0}, {"hr": 0}, {"hr": 150}, {"hr": 160}],
            "hr",
        )
        assert avg == 155.0
        assert max_val == 160.0

    def test_all_hr_zeros_returns_zero_pair(self):
        # After filtering all zeros the value list is empty → (0, 0).
        assert calculate_avg_and_max([{"hr": 0}, {"hr": 0}], "hr") == (0.0, 0.0)

    def test_exclude_zeros_flag_strips_zeros_for_non_hr_stream(self):
        avg, max_val = calculate_avg_and_max(
            [{"power": 0}, {"power": 200}, {"power": 300}],
            "power",
            exclude_zeros=True,
        )
        assert avg == 250.0
        assert max_val == 300.0


class TestCalculateNP:
    def test_returns_zero_for_empty_data(self):
        assert calculate_np([]) == 0

    def test_returns_zero_for_missing_power_key(self):
        assert calculate_np([{"hr": 140}]) == 0

    def test_returns_zero_for_none_power(self):
        assert calculate_np([{"power": None}]) == 0

    def test_normalized_power_single_value(self):
        assert calculate_np([{"power": 200}]) == 200.0

    def test_normalized_power_multiple_values(self):
        data = [{"power": 200}, {"power": 150}, {"power": 250}]
        result = calculate_np(data)
        expected = (200**4 + 150**4 + 250**4) / 3
        expected = expected ** (1 / 4)
        assert result == expected

    def test_returns_zero_on_value_error(self):
        result = calculate_np([{"power": "not_a_number"}])
        assert result == 0

    def test_returns_zero_on_key_error(self):
        result = calculate_np([{"no_power": 200}])
        assert result == 0


class TestCalculatePaceAcrossDstAndOffsets:
    """Duration math must run on the aware instants, not on stripped wall clocks.

    Reformatting both bounds through ``strftime``/``fromisoformat`` dropped their
    offsets purely to make them subtractable, which silently produced the wrong
    elapsed time whenever the two carried different offsets.
    """

    def test_duration_is_correct_across_a_dst_transition(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        import modules.activities.computation as computation

        lisbon = ZoneInfo("Europe/Lisbon")
        # Lisbon springs forward 01:00 -> 02:00 on 2024-03-31: the wall clock
        # advances 2h while only 1h of real time elapses.
        start = datetime(2024, 3, 31, 0, 30, tzinfo=lisbon)
        end = datetime(2024, 3, 31, 2, 30, tzinfo=lisbon)

        pace = computation.calculate_pace(1000, start, end)

        assert pace == 3600 / 1000  # one real hour, not two

    def test_duration_is_correct_for_mixed_offsets(self):
        from datetime import UTC, datetime, timedelta, timezone

        import modules.activities.computation as computation

        start = datetime(2024, 1, 15, 10, 0, tzinfo=timezone(timedelta(hours=2)))
        end = datetime(2024, 1, 15, 8, 30, tzinfo=UTC)  # 30 minutes after 08:00Z

        pace = computation.calculate_pace(600, start, end)

        assert pace == 1800 / 600

    def test_zero_distance_returns_zero(self):
        from datetime import UTC, datetime

        import modules.activities.computation as computation

        now = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        assert computation.calculate_pace(0, now, now) == 0


class TestElevationSmoothing:
    def test_parity_with_mobile_app(self):
        elevations = [100 + 0.5 * i + (4 if i % 2 == 0 else -4) for i in range(60)]
        gain, loss = compute_elevation_gain_and_loss([{"ele": e} for e in elevations])
        assert gain == pytest.approx(22.3956043956, abs=1e-6)
        assert loss == 0

    def test_stream_smoothing_keeps_time_and_matches_gain(self):
        elevations = [100 + 0.5 * i + (4 if i % 2 == 0 else -4) for i in range(60)]
        stream = [{"time": f"t{i}", "ele": e} for i, e in enumerate(elevations)]
        smoothed = smooth_elevation_stream(stream)
        assert [w["time"] for w in smoothed] == [w["time"] for w in stream]
        assert max(abs(b["ele"] - a["ele"]) for a, b in itertools.pairwise(smoothed)) < 1.3
        gain, _ = compute_elevation_gain_and_loss(stream, median_window=1, avg_window=1)
        assert gain > 100
        smoothed_gain, _ = compute_elevation_gain_and_loss(smoothed, median_window=1, avg_window=1)
        assert smoothed_gain == pytest.approx(22.3956043956, abs=1e-6)

    def test_stream_smoothing_returns_input_on_invalid_data(self):
        stream = [{"time": "t", "ele": None}]
        assert smooth_elevation_stream(stream) == stream


class TestRunningCadenceNormalization:
    def test_double_running_cadence_folds_fractional(self):
        # (85 + 0.328125) * 2 = 170.66 -> 171.
        assert double_running_cadence(85, 0.328125) == 171
        assert double_running_cadence(93, 0.0) == 186
        assert double_running_cadence(90) == 180
        assert double_running_cadence(85, None) == 170
        assert double_running_cadence(None) is None

    def test_double_cadence_waypoints_keeps_none_samples(self):
        waypoints = [{"time": "t0", "cad": 85}, {"time": "t1", "cad": None}, {"time": "t2", "cad": 87.4}]

        assert double_cadence_waypoints(waypoints) == [
            {"time": "t0", "cad": 170},
            {"time": "t1", "cad": None},
            {"time": "t2", "cad": 175},
        ]


class TestPauseThresholdSeconds:
    """Test suite for pause_threshold_seconds."""

    def test_dense_track_uses_the_minimum(self):
        """1 s sampling keeps the minimum threshold."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        times = [t + timedelta(seconds=i) for i in range(10)]
        assert (
            activities_computation.pause_threshold_seconds(times)
            == activities_computation.PAUSE_DETECTION_THRESHOLD_SECONDS
        )

    def test_sparse_track_scales_with_the_median_interval(self):
        """30 s sampling raises the threshold to three intervals."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        times = [t + timedelta(seconds=30 * i) for i in range(10)]
        assert activities_computation.pause_threshold_seconds(times) == 90.0

    def test_long_pauses_do_not_move_the_median(self):
        """Two 600 s pauses in a 1 s track keep the minimum threshold."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        offsets = [*range(10), 610, 611, 612, 1212, 1213, 1214]
        times = [t + timedelta(seconds=s) for s in offsets]
        assert (
            activities_computation.pause_threshold_seconds(times)
            == activities_computation.PAUSE_DETECTION_THRESHOLD_SECONDS
        )

    def test_no_positive_gap_uses_the_minimum(self):
        """Empty, single or duplicate timestamps fall back to the minimum."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        assert (
            activities_computation.pause_threshold_seconds([])
            == activities_computation.PAUSE_DETECTION_THRESHOLD_SECONDS
        )
        assert (
            activities_computation.pause_threshold_seconds([t, t])
            == activities_computation.PAUSE_DETECTION_THRESHOLD_SECONDS
        )

    def test_too_few_gaps_use_the_minimum(self):
        """A single 300 s gap is a pause, not a sampling interval."""
        t = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        times = [t, t + timedelta(seconds=300)]
        assert (
            activities_computation.pause_threshold_seconds(times)
            == activities_computation.PAUSE_DETECTION_THRESHOLD_SECONDS
        )


class TestHeldSeconds:
    def test_each_sample_holds_the_time_to_the_next_and_the_last_holds_nothing(self):
        assert activities_computation.held_seconds([0.0, 1.0, 3.0, 6.0], 15.0).tolist() == [1.0, 2.0, 3.0, 0.0]

    def test_a_gap_over_the_threshold_is_capped_at_it(self):
        assert activities_computation.held_seconds([0.0, 100.0, 101.0], 15.0).tolist() == [15.0, 1.0, 0.0]

    def test_samples_on_one_instant_share_its_time_equally(self):
        assert activities_computation.held_seconds([0.0, 0.0, 2.0, 2.0], 15.0).tolist() == [1.0, 1.0, 0.0, 0.0]

    def test_a_single_instant_and_no_samples_hold_nothing(self):
        assert activities_computation.held_seconds([5.0, 5.0], 15.0).tolist() == [0.0, 0.0]
        assert activities_computation.held_seconds([], 15.0).tolist() == []


class TestTimeWeightedMean:
    def test_uniform_sampling_equals_the_plain_mean(self):
        times = [float(i) for i in range(11)]
        values = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0, 180.0, 190.0, 200.0]

        # The last sample weighs nothing: the mean of the first ten.
        assert time_weighted_mean(times, values, 15.0) == pytest.approx(sum(values[:-1]) / 10)

    def test_a_held_value_weighs_the_time_it_was_held(self):
        # Smart recording: ten samples at 1 s of 100, then 200 held for 10 s before the next sample.
        times = [float(i) for i in range(11)] + [20.0]
        values = [100.0] * 10 + [200.0, 0.0]

        # (10 * 1 * 100 + 10 * 200) / 20 = 150, not the sample mean of about 109.
        assert time_weighted_mean(times, values, 15.0) == pytest.approx(150.0)

    def test_a_gap_longer_than_the_threshold_weighs_only_the_threshold(self):
        times = [0.0, 10.0, 1000.0]
        values = [100.0, 200.0, 0.0]

        # 100 weighs 10 s; 200 weighs 15 s (its 990 s gap capped); the last sample weighs nothing.
        assert time_weighted_mean(times, values, 15.0) == pytest.approx((100 * 10 + 200 * 15) / 25)

    def test_none_values_leave_out_their_time_and_the_previous_weight_runs_on(self):
        times = [0.0, 1.0, 2.0, 3.0, 4.0]
        values = [100.0, None, None, 200.0, 300.0]

        # 100 runs to the next kept sample (3 s), 200 for 1 s; 300 is last.
        assert time_weighted_mean(times, values, 15.0) == pytest.approx((100 * 3 + 200 * 1) / 4)

    def test_a_skipped_stretch_is_still_capped(self):
        times = [0.0, 1.0, 100.0, 101.0]
        values = [100.0, None, 200.0, 300.0]

        # 100 runs to 100 s, capped at 15 s; 200 for 1 s.
        assert time_weighted_mean(times, values, 15.0) == pytest.approx((100 * 15 + 200 * 1) / 16)

    def test_a_single_sample_averages_to_itself(self):
        assert time_weighted_mean([5.0], [140.0], 15.0) == 140.0

    def test_a_single_kept_sample_averages_to_itself(self):
        assert time_weighted_mean([0.0, 1.0, 2.0], [None, 90.0, None], 15.0) == 90.0

    def test_no_values_gives_none(self):
        assert time_weighted_mean([], [], 15.0) is None
        assert time_weighted_mean([0.0, 1.0], [None, None], 15.0) is None

    def test_sub_second_steps_are_weighted_by_their_real_length(self):
        times = [0.0, 0.5, 2.0]
        values = [100.0, 200.0, 0.0]

        # 100 for 0.5 s, 200 for 1.5 s.
        assert time_weighted_mean(times, values, 15.0) == pytest.approx((100 * 0.5 + 200 * 1.5) / 2.0)

    def test_samples_sharing_an_instant_share_its_time_equally(self):
        # Two sensors' worth of samples on whole-second stamps: 0 and 3 at each second, each pair holding 1 s.
        times = [0.0, 0.0, 1.0, 1.0, 2.0]
        values = [0.0, 3.0, 0.0, 3.0, 9.0]

        assert time_weighted_mean(times, values, 15.0) == pytest.approx(1.5)

    def test_samples_all_on_one_instant_average_plainly(self):
        assert time_weighted_mean([5.0, 5.0, 5.0], [100.0, 200.0, 300.0], 15.0) == pytest.approx(200.0)


def _reference_normalized_power(watts: list[float]) -> float:
    """Return Coggan's NP of a 1 Hz power list in plain Python: 30-sample rolling mean, 4th-power mean, 4th root."""
    rolling = [sum(watts[i : i + 30]) / 30 for i in range(len(watts) - 29)]
    return (sum(w**4 for w in rolling) / len(rolling)) ** 0.25


def _on_off(seconds: int, on: float = 400.0, off: float = 100.0, period: int = 30) -> list[float]:
    return [on if (second // period) % 2 == 0 else off for second in range(seconds)]


class TestNormalizedPower:
    def test_thirty_second_on_off_intervals_match_the_reference_and_the_plans_figure(self):
        watts = _on_off(600)

        result = normalized_power([float(i) for i in range(600)], watts, 15.0)

        assert result == pytest.approx(_reference_normalized_power(watts))
        # The plan's note quotes about 287.5 W for this ride.
        assert result == pytest.approx(287.5, abs=1.0)

    def test_steady_power_is_itself(self):
        assert normalized_power([float(i) for i in range(120)], [200.0] * 120, 15.0) == pytest.approx(200.0)

    def test_under_thirty_seconds_of_power_gives_none(self):
        assert normalized_power([float(i) for i in range(29)], [200.0] * 29, 15.0) is None
        assert normalized_power([], [], 15.0) is None
        assert normalized_power([0.0, 1.0], [None, None], 15.0) is None

    def test_exactly_thirty_seconds_give_one_window(self):
        assert normalized_power([float(i) for i in range(30)], [250.0] * 30, 15.0) == pytest.approx(250.0)

    def test_a_pause_leaves_the_result_unchanged(self):
        watts = _on_off(600)
        times = [float(i) for i in range(600)]
        paused_times = times[:300] + [t + 600.0 for t in times[300:]]

        assert normalized_power(paused_times, watts, 15.0) == pytest.approx(normalized_power(times, watts, 15.0))

    def test_smart_recording_equals_the_one_hertz_profile(self):
        watts = _on_off(600, period=30)
        # Samples only where the value changes, plus a 5 s heartbeat: each holds its value until the next.
        times = [float(i) for i in range(0, 600, 5)] + [599.0]
        values = [watts[int(t)] for t in times]

        assert normalized_power(times, values, 15.0) == pytest.approx(_reference_normalized_power(watts))

    def test_missing_power_is_left_out_with_its_time(self):
        # The None second is held by the previous sample, so it is the 1 Hz series with 200 W throughout.
        times = [float(i) for i in range(60)]
        values: list[float | None] = [200.0] * 60
        values[10] = None
        values[11] = None

        assert normalized_power(times, values, 15.0) == pytest.approx(200.0)

    def test_zeros_count(self):
        coasting = [250.0] * 60 + [0.0] * 60 + [250.0] * 60
        steady = [250.0] * 180

        with_zeros = normalized_power([float(i) for i in range(180)], coasting, 15.0)

        assert with_zeros == pytest.approx(_reference_normalized_power(coasting))
        assert with_zeros < normalized_power([float(i) for i in range(180)], steady, 15.0)

    def test_sub_second_samples_hold_the_latest_value_at_each_whole_second(self):
        # Four samples per second; every second holds the latest sample at or before it: 100 W, then 300 W.
        times = [i * 0.25 for i in range(480)]
        values = [100.0 if t < 60.0 else 300.0 for t in times]

        result = normalized_power(times, values, 15.0)

        reference = [100.0] * 60 + [300.0] * 60
        assert result == pytest.approx(_reference_normalized_power(reference))

    def test_sub_second_samples_within_a_second_are_averaged_by_their_time(self):
        # A 4 Hz power meter alternating 100 and 300 W: every second averages 200 W, none is one reading alone.
        times = [i * 0.25 for i in range(480)]
        values = [100.0 if i % 2 == 0 else 300.0 for i in range(480)]

        assert normalized_power(times, values, 15.0) == pytest.approx(200.0)

    def test_samples_on_one_instant_share_it_as_their_mean(self):
        times = [float(i // 2) for i in range(120)]
        values = [100.0, 300.0] * 60

        assert normalized_power(times, values, 15.0) == pytest.approx(200.0)

    def test_a_gap_longer_than_the_threshold_adds_no_seconds(self):
        # 20 s before a 100 s pause and 20 s after: 40 s of power, not 140.
        times = [float(i) for i in range(20)] + [float(i) + 120.0 for i in range(20)]

        assert normalized_power(times, [200.0] * 40, 15.0) == pytest.approx(200.0)
        assert normalized_power(times[:20] + times[20:29], [200.0] * 29, 15.0) is None


def _gain_and_loss(times, values) -> tuple[float, float]:
    """Return the activity gain and loss of a series: the sums of its per-sample counts."""
    smoothed = activities_computation.smooth_elevation(times, values)
    gains, losses = activities_computation.elevation_steps(smoothed)
    return sum(gains), sum(losses)


class TestSmoothElevation:
    """A centred 10 s time-window mean."""

    def test_at_one_hertz_each_sample_averages_every_sample_within_five_seconds(self):
        times = [float(t) for t in range(21)]
        values = [0.0 if t < 10 else 11.0 for t in range(21)]

        smoothed = activities_computation.smooth_elevation(times, values)

        # 5 s to 15 s: five samples of 0 and six of 11.
        assert smoothed[10] == pytest.approx(6.0)
        assert smoothed[0] == pytest.approx(0.0)

    def test_a_sample_six_seconds_away_is_outside_the_window_at_one_hertz(self):
        smoothed = activities_computation.smooth_elevation([float(t) for t in range(7)], [0.0] * 6 + [10.0])

        assert smoothed[0] == pytest.approx(0.0)

    def test_sparse_sampling_widens_the_window_to_ten_samples(self):
        # One sample every 10 s: the window spans 100 s, ten sample gaps, as 10 s does at 1 Hz.
        times = [float(t) for t in range(0, 210, 10)]
        values = [0.0 if t < 100 else 11.0 for t in range(0, 210, 10)]

        smoothed = activities_computation.smooth_elevation(times, values)

        # 50 s to 150 s: five samples of 0 and six of 11.
        assert smoothed[10] == pytest.approx(6.0)

    def test_sub_second_samples_all_count_in_the_window(self):
        times = [i * 0.25 for i in range(81)]
        values = [100.0 + 2.0 * t for t in times]

        smoothed = activities_computation.smooth_elevation(times, values)

        # A line is its own centred mean away from the ends.
        assert smoothed[40] == pytest.approx(values[40])
        assert len(smoothed) == len(values)

    def test_the_result_does_not_depend_on_the_order_of_the_samples(self):
        times = [0.0, 1.0, 2.0, 3.0, 9.0, 10.0]
        values = [1.0, 5.0, 2.0, 8.0, 3.0, 4.0]
        order = [3, 0, 5, 1, 4, 2]

        smoothed = activities_computation.smooth_elevation(times, values)
        shuffled = activities_computation.smooth_elevation([times[i] for i in order], [values[i] for i in order])

        assert shuffled == pytest.approx([smoothed[i] for i in order])

    def test_no_samples_give_no_series(self):
        assert activities_computation.smooth_elevation([], []) == []


class TestElevationSteps:
    """A 3 m hysteresis, counted at the sample where each rise or drop is confirmed."""

    def test_a_series_that_stays_within_three_metres_counts_nothing(self):
        assert activities_computation.elevation_steps([100.0, 102.9, 97.1, 100.0]) == ([0.0] * 4, [0.0] * 4)

    def test_a_rise_of_three_metres_is_counted_and_moves_the_reference(self):
        gains, losses = activities_computation.elevation_steps([100.0, 103.0, 105.0, 106.0, 100.0])

        assert gains == [0.0, 3.0, 0.0, 3.0, 0.0]
        assert losses == [0.0, 0.0, 0.0, 0.0, 6.0]

    def test_no_samples_count_nothing(self):
        assert activities_computation.elevation_steps([]) == ([], [])


class TestElevationFromNoisyStreams:
    """The activity gain and loss follow the terrain, not the sampling rate or the noise."""

    @staticmethod
    def _flat_hour(step: int, noise: float) -> tuple[list[float], list[float]]:
        rng = np.random.default_rng(7)
        times = [float(t) for t in range(0, 3600, step)]
        return times, [100.0 + float(rng.normal(0.0, noise)) for _ in times]

    @pytest.mark.parametrize(("step", "noise"), [(1, 1.5), (5, 1.5), (10, 1.5)])
    def test_a_flat_hour_with_noise_gains_and_loses_nothing(self, step, noise):
        gain, loss = _gain_and_loss(*self._flat_hour(step, noise))

        assert gain < 1.0
        assert loss < 1.0

    def test_a_climb_and_a_descent_count_their_height(self):
        times = [float(t) for t in range(2001)]
        values = [100.0 + min(t, 2000 - t) / 10.0 for t in times]

        gain, loss = _gain_and_loss(times, values)

        assert gain == pytest.approx(100.0, abs=3.0)
        assert loss == pytest.approx(100.0, abs=3.0)

    def test_a_staircase_of_steps_below_the_threshold_is_counted(self):
        times = [float(t) for t in range(0, 600)]
        values = [100.0 + 2.0 * min(t // 50, 10) for t in range(600)]

        gain, loss = _gain_and_loss(times, values)

        assert gain == pytest.approx(20.0, abs=3.0)
        assert loss == 0.0


class TestCalculateStepSpeed:
    """Speed between two positions is the distance over the real time step."""

    _START = datetime(2024, 1, 15, 8, 0, 0)

    def _speed(self, seconds: float, lon: float = 0.000009) -> float:
        return activities_computation.calculate_step_speed(
            self._START, self._START + timedelta(seconds=seconds), 0.0, lon, 0.0, 0.0
        )

    def test_a_subsecond_step_is_not_clamped_to_one_second(self):
        metres = geodesic((0.0, 0.0), (0.0, 0.000009)).meters

        # 1 m in 0.2 s is 5 m/s; clamped to 1 s it would be 1 m/s.
        assert self._speed(0.2) == pytest.approx(metres / 0.2)
        assert self._speed(0.2) == pytest.approx(5.0, rel=0.02)

    def test_a_whole_second_step_is_distance_over_seconds(self):
        metres = geodesic((0.0, 0.0), (0.0, 0.000045)).meters

        assert self._speed(2.0, lon=0.000045) == pytest.approx(metres / 2.0)

    def test_a_step_whose_clock_does_not_advance_has_no_speed(self):
        assert self._speed(0.0) == 0
        assert self._speed(-3.0) == 0

    def test_a_missing_previous_position_has_no_speed(self):
        assert activities_computation.calculate_step_speed(None, self._START, 0.0, 0.1, None, None) == 0


class TestDisplacementSpeeds:
    """The speed over a centred 10 s window, from the straight-line distance it covers."""

    @staticmethod
    def _speeds(times, lons, run_starts=frozenset()):
        return activities_computation.displacement_speeds(
            [float(t) for t in times], [0.0 if lon is not None else None for lon in lons], lons, run_starts
        )

    def test_jitter_around_one_place_is_slow_though_every_step_is_fast(self):
        wobble = 2.5 / 111_319.49
        speeds = self._speeds(range(60), [1.0 + wobble * (i % 2) for i in range(60)])

        assert max(speed for speed in speeds if speed is not None) < 0.5

    def test_steady_walking_keeps_its_speed(self):
        step = 1.2 / 111_319.49
        speeds = self._speeds(range(60), [1.0 + step * i for i in range(60)])

        assert speeds[30] == pytest.approx(1.2, rel=0.01)

    def test_a_sample_without_a_position_has_no_speed(self):
        speeds = self._speeds(range(3), [1.0, None, 1.00001])

        assert speeds[1] is None

    def test_the_window_stays_inside_its_run(self):
        step = 3.0 / 111_319.49
        # A run that ends standing, then a new run 100 m away: the window of the run's last sample ignores the jump.
        lons = [1.0 + step * i for i in range(10)] + [1.0 + step * 9] * 5 + [1.001 + step * i for i in range(10)]
        speeds = self._speeds(range(25), lons, frozenset({15}))

        assert speeds[14] < 3.0
        assert speeds[15] == pytest.approx(3.0, rel=0.05)


class TestMovingTime:
    """Moving time counts the steps at 0.5 m/s or more, within the pause threshold."""

    @staticmethod
    def _moving(times, speeds, max_gap=15.0) -> float:
        return activities_computation.moving_time([float(t) for t in times], speeds, max_gap)

    def test_standing_still_with_gps_jitter_is_not_moving(self):
        speeds = [0.3 if i % 2 else 0.1 for i in range(601)]

        # The old gap-only rule counted 600 s.
        assert self._moving(range(601), speeds) == 0.0

    def test_walking_counts_every_step(self):
        assert self._moving(range(601), [1.2] * 601) == pytest.approx(600.0)

    def test_a_stop_at_a_light_is_not_moving(self):
        speeds = [5.0] * 300 + [0.0] * 120 + [5.0] * 181

        assert self._moving(range(601), speeds) == pytest.approx(480.0)

    def test_a_step_across_a_gap_over_the_threshold_is_not_moving(self):
        times = [0, 1, 2, 202, 203, 204]

        assert self._moving(times, [3.0] * 6) == pytest.approx(4.0)

    def test_a_step_exactly_at_the_threshold_is_moving(self):
        assert self._moving([0, 15, 30], [3.0] * 3) == pytest.approx(30.0)

    def test_a_speed_of_exactly_half_a_metre_per_second_is_moving(self):
        assert self._moving([0, 1, 2], [0.5, 0.5, 0.5]) == pytest.approx(2.0)

    def test_the_speed_of_the_sample_ending_a_step_decides_it(self):
        assert self._moving([0, 10, 20], [None, 0.0, 2.0]) == pytest.approx(10.0)

    def test_steps_without_a_speed_count_by_the_gap_rule_alone(self):
        times = [0, 10, 20, 400, 410]

        assert self._moving(times, [None] * 5) == pytest.approx(30.0)

    def test_a_step_with_no_speed_among_known_ones_counts_by_the_gap_rule(self):
        assert self._moving([0, 5, 10, 15], [1.0, None, 0.0, 2.0]) == pytest.approx(10.0)

    def test_duplicate_and_out_of_order_times_add_nothing(self):
        assert self._moving([0, 10, 10, 5, 15], [1.0, 2.0, 2.0, 2.0, 2.0]) == pytest.approx(15.0)

    def test_fewer_than_two_samples_have_no_moving_time(self):
        assert self._moving([], []) == 0.0
        assert self._moving([5], [3.0]) == 0.0

    def test_subsecond_steps_sum_to_their_real_duration(self):
        times = [0.0, 0.2, 0.4, 0.6]

        assert activities_computation.moving_time(times, [2.0] * 4, 15.0) == pytest.approx(0.6)


class TestRollingMaxSpeed:
    """Max speed is the best 5 s time-window mean of the measured speeds."""

    @staticmethod
    def _peak(times, speeds, max_gap=15.0):
        return activities_computation.rolling_max_speed([float(t) for t in times], speeds, max_gap)

    def test_a_one_second_spike_is_averaged_over_five_seconds(self):
        speeds = [5.0] * 61
        speeds[30] = 15.0

        # The window holds the spike and four ordinary seconds: (15 + 4 x 5) / 5.
        assert self._peak(range(61), speeds) == pytest.approx(7.0)

    def test_the_old_five_sample_median_would_have_hidden_the_spike_entirely(self):
        speeds = [5.0] * 61
        speeds[30] = 15.0

        assert activities_computation.calculate_robust_max(speeds) == 5.0
        assert self._peak(range(61), speeds) > 6.9

    def test_the_window_is_over_time_not_samples_at_five_second_sampling(self):
        speeds = [5.0, 5.0, 9.0, 5.0, 5.0]

        # One sample spans the whole 5 s window, so it is the window's mean.
        assert self._peak([0, 5, 10, 15, 20], speeds) == pytest.approx(9.0)

    def test_a_faster_recording_averages_more_samples(self):
        times = [i * 0.5 for i in range(121)]
        speeds = [5.0] * 121
        speeds[60] = 15.0

        # Half a second of 15 and 4.5 s of 5.
        assert self._peak(times, speeds) == pytest.approx((15 * 0.5 + 5 * 4.5) / 5)

    def test_a_sustained_burst_is_reported_in_full(self):
        speeds = [3.0] * 20 + [9.0] * 5 + [3.0] * 20

        assert self._peak(range(45), speeds) == pytest.approx(9.0)

    def test_a_placeholder_is_not_a_measurement(self):
        speeds: list[float | None] = [None] + [4.0] * 10

        assert self._peak(range(11), speeds) == pytest.approx(4.0)

    def test_a_placeholder_zero_does_not_pull_a_window_down(self):
        speeds: list[float | None] = [None, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0]

        assert self._peak(range(7), speeds) == pytest.approx(6.0)

    def test_a_step_across_a_gap_over_the_threshold_is_not_a_measurement(self):
        times = [*range(10), 200]
        speeds: list[float | None] = [4.0] * 10 + [40.0]

        assert self._peak(times, speeds) == pytest.approx(4.0)

    def test_a_window_does_not_span_a_gap(self):
        times = list(range(4)) + list(range(100, 104))
        speeds: list[float | None] = [8.0] * 4 + [None] + [2.0] * 3

        # Neither run holds 5 s: the plain maximum of the measured speeds.
        assert self._peak(times, speeds) == pytest.approx(8.0)

    def test_without_five_seconds_of_speed_the_plain_maximum_is_returned(self):
        assert self._peak([0, 1, 2, 3], [None, 4.0, 10.0, 3.0]) == pytest.approx(10.0)

    def test_samples_sharing_an_instant_share_it_as_their_mean(self):
        # A pair 0 and 6 m/s in every second is 3 m/s over time, not 6.
        times = [t for t in range(11) for _ in range(2)]
        speeds = [v for _ in range(11) for v in (0.0, 6.0)]

        assert self._peak(times, speeds) == pytest.approx(3.0)

    def test_a_placeholder_sharing_an_instant_with_a_measurement_is_left_out(self):
        times = [t for t in range(11) for _ in range(2)]
        speeds = [v for _ in range(11) for v in (4.0, None)]

        assert self._peak(times, speeds) == pytest.approx(4.0)

    def test_no_measured_speed_gives_none(self):
        assert self._peak([0, 1, 2], [None, None, None]) is None
        assert self._peak([], []) is None


class TestLapCloses:
    """Laps close at multiples of the lap length over the cumulative distance."""

    def test_the_step_that_reaches_a_multiple_closes_the_lap_and_the_remainder_is_the_last_lap(self):
        steps = [0.0] + [400.0] * 7

        assert activities_computation.lap_closes(steps, 1000.0) == [3, 5, 7]

    def test_a_step_over_several_multiples_closes_one_lap_and_the_next_multiple_follows(self):
        steps = [0.0, 2500.0, 400.0, 700.0]

        assert activities_computation.lap_closes(steps, 1000.0) == [1, 3]

    def test_standing_after_the_last_full_lap_belongs_to_that_lap(self):
        steps = [0.0, 1000.0, 0.0, 0.0]

        assert activities_computation.lap_closes(steps, 1000.0) == [3]

    def test_no_distance_gives_no_lap(self):
        assert activities_computation.lap_closes([0.0, 0.0, 0.0], 1000.0) == []
        assert activities_computation.lap_closes([], 1000.0) == []

    def test_distance_short_of_a_lap_is_one_lap(self):
        assert activities_computation.lap_closes([0.0, 300.0, 200.0], 1000.0) == [2]


class TestMovingSteps:
    """The per-sample moving distances and durations add up to the totals."""

    def test_distances_and_durations_sum_to_the_totals_and_leave_a_pause_out(self):
        times = [0.0, 1.0, 2.0, 300.0, 301.0]
        lats = [0.0] * 5
        lons = [0.0, 0.0001, 0.0002, 0.0003, 0.0004]
        speeds = [None, 11.1, 11.1, 0.0, 11.1]

        distances = activities_computation.moving_step_distances(times, lats, lons, speeds, 15.0, {3})
        durations = activities_computation.moving_durations(times, speeds, 15.0)

        assert distances[3] == 0.0
        assert durations == [0.0, 1.0, 1.0, 0.0, 1.0]
        assert sum(distances) == activities_computation.moving_distance(times, lats, lons, speeds, 15.0, {3})
        assert sum(durations) == activities_computation.moving_time(times, speeds, 15.0)
