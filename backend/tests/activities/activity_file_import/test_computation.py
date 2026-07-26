"""Tests for the file-import metric computation helpers.

Relocated from ``tests/activities/activity/test_utils*`` when the stream-math
moved out of the activities core into ``activity_file_import/computation.py``.
"""

from datetime import datetime

from modules.activities.activity_file_import.computation import (
    append_if_not_none,
    calculate_avg_and_max,
    calculate_instant_speed,
    calculate_np,
    calculate_pace,
    compute_elevation_gain_and_loss,
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


class TestComputeElevationGainAndLoss:
    def test_returns_zero_for_empty_list(self):
        assert compute_elevation_gain_and_loss([]) == (0.0, 0.0)

    def test_returns_zero_for_invalid_data(self):
        assert compute_elevation_gain_and_loss([{"no_ele": 100}]) == (0.0, 0.0)

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


class TestAppendIfNotNone:
    def test_appends_when_value_not_none(self):
        waypoints = []
        append_if_not_none(waypoints, waypoint_time="2024-01-15T08:00:00", value=145, key="hr")
        assert len(waypoints) == 1
        assert waypoints[0]["hr"] == 145

    def test_does_not_append_when_none(self):
        waypoints = []
        append_if_not_none(waypoints, waypoint_time="2024-01-15T08:00:00", value=None, key="hr")
        assert len(waypoints) == 0


class TestCalculatePaceAcrossDstAndOffsets:
    """Duration math must run on the aware instants, not on stripped wall clocks.

    Reformatting both bounds through ``strftime``/``fromisoformat`` dropped their
    offsets purely to make them subtractable, which silently produced the wrong
    elapsed time whenever the two carried different offsets.
    """

    def test_duration_is_correct_across_a_dst_transition(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        import modules.activities.activity_file_import.computation as computation

        lisbon = ZoneInfo("Europe/Lisbon")
        # Lisbon springs forward 01:00 -> 02:00 on 2024-03-31: the wall clock
        # advances 2h while only 1h of real time elapses.
        start = datetime(2024, 3, 31, 0, 30, tzinfo=lisbon)
        end = datetime(2024, 3, 31, 2, 30, tzinfo=lisbon)

        pace = computation.calculate_pace(1000, start, end)

        assert pace == 3600 / 1000  # one real hour, not two

    def test_duration_is_correct_for_mixed_offsets(self):
        from datetime import UTC, datetime, timedelta, timezone

        import modules.activities.activity_file_import.computation as computation

        start = datetime(2024, 1, 15, 10, 0, tzinfo=timezone(timedelta(hours=2)))
        end = datetime(2024, 1, 15, 8, 30, tzinfo=UTC)  # 30 minutes after 08:00Z

        pace = computation.calculate_pace(600, start, end)

        assert pace == 1800 / 600

    def test_zero_distance_returns_zero(self):
        from datetime import UTC, datetime

        import modules.activities.activity_file_import.computation as computation

        now = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        assert computation.calculate_pace(0, now, now) == 0
