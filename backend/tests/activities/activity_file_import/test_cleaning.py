"""Tests that cleaning merges duplicate times, drops null island, heart rate zeros and speeds above the sport's cap."""

from datetime import UTC, datetime, timedelta

import pytest

import modules.activities.activity_file_import.cleaning as cleaning
import modules.activities.activity_file_import.recording as recording
from tests.activities.activity_file_import import assembled
from tests.activities.activity_file_import.assembled import assemble_recording, make_recording, session

_T0 = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)

#: Degrees of latitude that are 155 metres.
_METRES_155 = 155 / 111_195


def _at(second: float) -> datetime:
    return _T0 + timedelta(seconds=second)


def _clean(rows, sport: str | None = "running") -> recording.Samples:
    return cleaning.clean_session(session(rows, sport=sport)).samples


def _track(sport: str | None, *lats: float) -> recording.Samples:
    return _clean([{"time": _at(index), "lat": lat, "lon": 10.0} for index, lat in enumerate(lats)], sport)


def test_duplicate_times_become_one_row_with_the_first_known_value_of_each_channel():
    samples = _clean(
        [
            {"time": _at(0), "heart_rate": 120},
            {"time": _at(1), "heart_rate": None, "power": 200, "cadence": 80.0},
            {"time": _at(1), "heart_rate": 130, "power": 250, "temperature": 20.0},
            {"time": _at(1), "heart_rate": 140, "cadence": 90.0},
            {"time": _at(2), "heart_rate": 150},
        ]
    )

    assert samples.time == (_at(0), _at(1), _at(2))
    assert samples.heart_rate == (120, 130, 150)
    assert samples.power == (None, 200, None)
    assert samples.cadence == (None, 80.0, None)
    assert samples.temperature == (None, 20.0, None)


def test_duplicate_times_take_the_position_as_a_pair_from_one_row():
    samples = _clean(
        [
            {"time": _at(1), "lat": 41.0, "lon": None},
            {"time": _at(1), "lat": 42.0, "lon": 11.0},
        ]
    )

    assert (samples.lat, samples.lon) == ((42.0,), (11.0,))


def test_a_position_at_null_island_is_cleared_and_the_other_channels_stay():
    samples = _clean(
        [
            {"time": _at(0), "lat": 41.0, "lon": 10.0},
            {"time": _at(1), "lat": 0.0, "lon": 0.0, "heart_rate": 140, "altitude": 12.0},
        ]
    )

    assert samples.lat == (41.0, None)
    assert samples.lon == (10.0, None)
    assert samples.heart_rate == (None, 140)
    assert samples.altitude == (None, 12.0)


def test_a_heart_rate_of_zero_is_a_dropout_but_zero_cadence_and_power_are_kept():
    samples = _clean(
        [
            {"time": _at(0), "heart_rate": 0, "cadence": 0.0, "power": 0},
            {"time": _at(1), "heart_rate": 90, "cadence": 80.0, "power": 150},
        ]
    )

    assert samples.heart_rate == (None, 90)
    assert samples.cadence == (0.0, 80.0)
    assert samples.power == (0, 150)


@pytest.mark.parametrize(
    ("sport", "speed", "expected"),
    [
        ("running", 13.0, None),
        ("running", 12.0, 12.0),
        ("walking", 13.0, None),
        ("hiking", 13.0, None),
        ("cycling", 13.0, 13.0),
        ("cycling", 35.0, 35.0),
        ("cycling", 36.0, None),
        ("virtualride", 36.0, None),
        ("swimming", 7.0, None),
        ("swimming", 6.0, 6.0),
        ("rowing", 7.0, None),
        ("kayaking", 7.0, None),
        ("stand_up_paddleboarding", 7.0, None),
        ("sailing", 7.0, None),
        ("windsurf", 7.0, None),
        ("surf", 7.0, None),
        ("yoga", 49.0, 49.0),
        ("yoga", 51.0, None),
        ("not a sport", 51.0, None),
        (None, 49.0, 49.0),
        (None, 51.0, None),
    ],
)
def test_a_device_speed_above_the_sports_cap_is_cleared(sport, speed, expected):
    samples = _clean([{"time": _at(0), "speed": 2.0}, {"time": _at(1), "speed": speed}], sport)

    assert samples.speed == (2.0, expected)


def test_a_device_distance_is_never_changed():
    samples = _clean([{"time": _at(0), "distance": 0.0, "speed": 99.0}, {"time": _at(1), "distance": 5000.0}])

    assert samples.distance == (0.0, 5000.0)


def test_a_one_sample_gps_jump_is_dropped_and_the_track_continues_from_the_last_kept_point():
    samples = _track("running", 41.0, 41.0 + _METRES_155, 41.00002, 41.00004)

    assert samples.lat == (41.0, None, 41.00002, 41.00004)
    assert samples.lon == (10.0, None, 10.0, 10.0)


def test_a_stale_first_fix_is_dropped_and_the_track_after_it_kept():
    # A watch's first fix can be where it last saw the sky; the track that follows agrees with itself.
    stale, start = 41.0, 41.0 + _METRES_155
    samples = _track("running", stale, start, start + 3 / 111_195, start + 6 / 111_195)

    assert samples.lat == (None, start, start + 3 / 111_195, start + 6 / 111_195)


def test_a_jump_right_after_the_first_fix_is_dropped_and_the_first_fix_kept():
    samples = _track("running", 41.0, 41.0 + _METRES_155, 41.0 + 3 / 111_195)

    assert samples.lat == (41.0, None, 41.0 + 3 / 111_195)


def test_two_consecutive_bad_points_are_both_dropped():
    samples = _track("running", 41.0, 41.0 + _METRES_155, 41.0 + 2 * _METRES_155, 41.00003)

    assert samples.lat == (41.0, None, None, 41.00003)


def test_a_step_is_compared_over_the_real_time_step_so_a_sub_second_step_is_stricter():
    # 5 metres: 5 m/s over one second is a run, 10 m/s over half a second is a run, 20 m/s over a quarter is not.
    metres_5 = 5 / 111_195
    rows = [
        {"time": _at(0), "lat": 41.0, "lon": 10.0},
        {"time": _at(0.5), "lat": 41.0 + metres_5, "lon": 10.0},
        {"time": _at(0.75), "lat": 41.0 + 2 * metres_5, "lon": 10.0},
    ]

    samples = _clean(rows)

    assert samples.lat == (41.0, 41.0 + metres_5, None)


def test_a_gap_in_the_track_is_compared_with_the_last_kept_point_over_the_time_since_it():
    # 155 m over 60 s is 2.6 m/s although the sample in between carries no position.
    rows = [
        {"time": _at(0), "lat": 41.0, "lon": 10.0},
        {"time": _at(30), "heart_rate": 130},
        {"time": _at(60), "lat": 41.0 + _METRES_155, "lon": 10.0},
    ]

    assert _clean(rows).lat == (41.0, None, 41.0 + _METRES_155)


def test_a_step_below_the_bike_cap_is_kept_on_a_ride_and_dropped_on_a_run():
    thirty_metres = 30 / 111_195

    assert _track("cycling", 41.0, 41.0 + thirty_metres).lat == (41.0, 41.0 + thirty_metres)
    assert _track("running", 41.0, 41.0 + thirty_metres).lat == (41.0, None)


def test_a_session_keeps_everything_but_its_samples():
    original = session([{"time": _at(0), "heart_rate": 0}], sport="cycling")

    cleaned = cleaning.clean_session(original)

    assert cleaned.sport == "cycling"
    assert cleaned.start_time == original.start_time
    assert cleaned.samples.heart_rate == (None,)


def test_assembly_cleans_a_session_before_it_builds_its_streams():
    rows = [{"time": _at(second), "heart_rate": 0 if second == 1 else 140} for second in range(3)]

    (payload,) = assemble_recording(make_recording(session(rows)))

    assert assembled.values(payload, "heart_rate") == [140, 140]
