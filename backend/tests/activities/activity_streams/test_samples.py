"""Pure maths of the columnar samples: converting stored waypoint streams, downsampling and deriving pace."""

from datetime import UTC, datetime

import pytest

import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.contracts as stream_contracts
import modules.activities.activity_streams.samples as samples
import modules.activities.activity_streams.schema as stream_schema

_START = datetime(2025, 3, 10, 8, 0, 0, tzinfo=UTC)
_TYPE = stream_constants.ActivityStreamType


def _at(seconds: int) -> str:
    """The stamp a file stream gives the sample ``seconds`` after the start."""
    return f"2025-03-10T08:{seconds // 60:02d}:{seconds % 60:02d}"


def _row(stream_type: _TYPE, waypoints: list[dict]) -> stream_schema.ActivityStreamsBase:
    return stream_schema.ActivityStreamsBase(
        activity_id="00000000-0000-0000-0000-000000000001",
        stream_type=stream_type.stored,
        stream_waypoints=waypoints,
    )


class TestSamplesFromStreams:
    def test_streams_of_one_file_become_one_timeline_in_milliseconds_from_the_start(self):
        rows = [
            _row(
                _TYPE.HEART_RATE,
                [{"time": _at(0), "hr": 100}, {"time": _at(1), "hr": 110}, {"time": _at(2), "hr": 120}],
            ),
            _row(
                _TYPE.POWER,
                [{"time": _at(0), "power": 200}, {"time": _at(1), "power": 210}, {"time": _at(2), "power": 220}],
            ),
            _row(
                _TYPE.CADENCE, [{"time": _at(0), "cad": 80}, {"time": _at(1), "cad": 82}, {"time": _at(2), "cad": 84}]
            ),
            _row(
                _TYPE.ELEVATION,
                [{"time": _at(0), "ele": 10.5}, {"time": _at(1), "ele": 11}, {"time": _at(2), "ele": 12}],
            ),
            _row(_TYPE.SPEED, [{"time": _at(0), "vel": 3}, {"time": _at(1), "vel": 3.5}, {"time": _at(2), "vel": 4}]),
            _row(
                _TYPE.TEMPERATURE,
                [{"time": _at(0), "temp": 20}, {"time": _at(1), "temp": 21}, {"time": _at(2), "temp": 22}],
            ),
            _row(
                _TYPE.MAP,
                [
                    {"time": _at(0), "lat": 38.0, "lon": -9.0},
                    {"time": _at(1), "lat": 38.1, "lon": -9.1},
                    {"time": _at(2), "lat": 38.2, "lon": -9.2},
                ],
            ),
        ]

        result = samples.samples_from_streams(rows, _START)

        assert result == stream_contracts.ParsedSamples(
            offsets_ms=[0, 1000, 2000],
            latitude=[38.0, 38.1, 38.2],
            longitude=[-9.0, -9.1, -9.2],
            elevation=[10.5, 11.0, 12.0],
            heart_rate=[100.0, 110.0, 120.0],
            power=[200.0, 210.0, 220.0],
            cadence=[80.0, 82.0, 84.0],
            speed=[3.0, 3.5, 4.0],
            temperature=[20.0, 21.0, 22.0],
        )

    def test_a_strava_stream_stamped_in_seconds_from_the_start_ignores_the_start_time(self):
        rows = [
            _row(_TYPE.HEART_RATE, [{"time": 0, "hr": 100}, {"time": 5, "hr": 110}]),
            _row(_TYPE.SPEED, [{"time": 0, "vel": 2.0}, {"time": 5, "vel": 2.5}]),
        ]

        result = samples.samples_from_streams(rows, _START)

        assert result is not None
        assert result.offsets_ms == [0, 5000]
        assert result.heart_rate == [100.0, 110.0]
        assert result.speed == [2.0, 2.5]

    def test_a_stamp_before_the_start_gives_a_negative_offset_and_a_zone_offset_is_honoured(self):
        rows = [
            _row(
                _TYPE.HEART_RATE,
                [{"time": "2025-03-10T07:59:58", "hr": 90}, {"time": "2025-03-10T09:00:01+01:00", "hr": 95}],
            )
        ]

        result = samples.samples_from_streams(rows, _START)

        assert result is not None
        assert result.offsets_ms == [-2000, 1000]

    def test_streams_with_different_instants_are_laid_on_the_union_and_a_dropout_is_none(self):
        rows = [
            _row(
                _TYPE.HEART_RATE,
                [{"time": _at(0), "hr": 100}, {"time": _at(1), "hr": 101}, {"time": _at(3), "hr": 103}],
            ),
            _row(
                _TYPE.POWER,
                [{"time": _at(0), "power": 200}, {"time": _at(2), "power": 202}, {"time": _at(3), "power": 203}],
            ),
        ]

        result = samples.samples_from_streams(rows, _START)

        assert result == stream_contracts.ParsedSamples(
            offsets_ms=[0, 1000, 2000, 3000],
            heart_rate=[100.0, 101.0, None, 103.0],
            power=[200.0, None, 202.0, 203.0],
        )

    def test_several_waypoints_under_one_stamp_stay_several_samples_in_order_and_align_by_occurrence(self):
        # A sub-second file stores 10.0, 10.3 and 10.6 s all as 08:00:10; the k-th waypoint of a stamp in every stream
        # is the same sample.
        rows = [
            _row(
                _TYPE.HEART_RATE,
                [
                    {"time": _at(9), "hr": 90},
                    {"time": _at(10), "hr": 100},
                    {"time": _at(10), "hr": 101},
                    {"time": _at(10), "hr": 102},
                ],
            ),
            _row(
                _TYPE.MAP,
                [
                    {"time": _at(10), "lat": 1.0, "lon": 2.0},
                    {"time": _at(10), "lat": 1.1, "lon": 2.1},
                    {"time": _at(10), "lat": 1.2, "lon": 2.2},
                ],
            ),
        ]

        result = samples.samples_from_streams(rows, _START)

        assert result == stream_contracts.ParsedSamples(
            offsets_ms=[9000, 10000, 10000, 10000],
            latitude=[None, 1.0, 1.1, 1.2],
            longitude=[None, 2.0, 2.1, 2.2],
            heart_rate=[90.0, 100.0, 101.0, 102.0],
        )

    def test_a_stream_with_fewer_waypoints_under_a_stamp_aligns_with_the_first_ones(self):
        rows = [
            _row(
                _TYPE.HEART_RATE,
                [{"time": _at(10), "hr": 100}, {"time": _at(10), "hr": 101}, {"time": _at(10), "hr": 102}],
            ),
            _row(_TYPE.POWER, [{"time": _at(10), "power": 250}]),
        ]

        result = samples.samples_from_streams(rows, _START)

        assert result is not None
        assert result.offsets_ms == [10000, 10000, 10000]
        assert result.heart_rate == [100.0, 101.0, 102.0]
        assert result.power == [250.0, None, None]

    def test_an_activity_with_only_a_map_stream_has_only_the_position_channels(self):
        rows = [
            _row(_TYPE.MAP, [{"time": _at(0), "lat": 38.0, "lon": -9.0}, {"time": _at(4), "lat": 38.1, "lon": -9.1}])
        ]

        result = samples.samples_from_streams(rows, _START)

        assert result == stream_contracts.ParsedSamples(
            offsets_ms=[0, 4000], latitude=[38.0, 38.1], longitude=[-9.0, -9.1]
        )

    def test_the_pace_stream_is_dropped_because_pace_is_derived_from_speed(self):
        rows = [
            _row(_TYPE.SPEED, [{"time": _at(0), "vel": 4.0}]),
            _row(_TYPE.PACE, [{"time": _at(0), "pace": 0.25}, {"time": _at(7), "pace": 0.5}]),
        ]

        result = samples.samples_from_streams(rows, _START)

        assert result == stream_contracts.ParsedSamples(offsets_ms=[0], speed=[4.0])

    def test_a_waypoint_without_a_usable_time_or_a_value_adds_no_sample_or_value(self):
        rows = [
            _row(
                _TYPE.HEART_RATE,
                [{"hr": 100}, {"time": "soon", "hr": 101}, {"time": _at(1), "hr": None}, {"time": _at(2), "hr": 102}],
            ),
        ]

        result = samples.samples_from_streams(rows, _START)

        assert result is not None
        assert result.offsets_ms == [1000, 2000]
        assert result.heart_rate == [None, 102.0]

    def test_a_stream_of_an_unknown_type_is_ignored(self):
        rows = [
            stream_schema.ActivityStreamsBase(
                activity_id="00000000-0000-0000-0000-000000000001", stream_type=99, stream_waypoints=[{"time": _at(3)}]
            ),
            _row(_TYPE.POWER, [{"time": _at(0), "power": 200}]),
        ]

        result = samples.samples_from_streams(rows, _START)

        assert result == stream_contracts.ParsedSamples(offsets_ms=[0], power=[200.0])

    @pytest.mark.parametrize(
        "rows",
        [
            [],
            [_row(_TYPE.HEART_RATE, [])],
            [_row(_TYPE.HEART_RATE, [{"time": _at(0), "hr": None}])],
            [_row(_TYPE.PACE, [{"time": _at(0), "pace": 0.25}])],
            [_row(_TYPE.MAP, [{"time": _at(0), "lat": None, "lon": None}])],
        ],
        ids=["no-streams", "empty-stream", "no-value", "pace-only", "no-position"],
    )
    def test_streams_that_hold_no_value_give_no_samples(self, rows):
        assert samples.samples_from_streams(rows, _START) is None

    def test_a_naive_start_is_read_as_utc(self):
        rows = [_row(_TYPE.HEART_RATE, [{"time": _at(2), "hr": 100}])]

        result = samples.samples_from_streams(rows, _START.replace(tzinfo=None))

        assert result is not None
        assert result.offsets_ms == [2000]


def _series(**channels):
    return stream_contracts.ParsedSamples(**channels)


class TestDownsample:
    def test_a_series_not_longer_than_the_bound_is_returned_unchanged(self):
        series = _series(offsets_ms=[0, 1000, 2000], heart_rate=[1.0, 2.0, 3.0])

        assert samples.downsample(series, 3) is series
        assert samples.downsample(series, 10) is series

    def test_samples_are_averaged_per_equal_time_bucket_over_the_first_to_last_offset(self):
        # Span 0..9000 in 3 buckets of 3000 ms: [0, 3000), [3000, 6000), [6000, 9000].
        series = _series(
            offsets_ms=[0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000],
            heart_rate=[100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0, 180.0, 190.0],
            speed=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        )

        result = samples.downsample(series, 3)

        assert result.offsets_ms == [1000, 4000, 7500]
        assert result.heart_rate == [110.0, 140.0, 175.0]
        assert result.speed == [2.0, 5.0, 8.5]
        assert result.power is None

    def test_the_mean_offset_is_rounded_to_a_whole_millisecond(self):
        series = _series(offsets_ms=[0, 1, 2, 10], heart_rate=[1.0, 2.0, 3.0, 4.0])

        result = samples.downsample(series, 2)

        # Buckets of 5 ms: [0, 5) holds 0, 1, 2 (mean 1); [5, 10] holds 10.
        assert result.offsets_ms == [1, 10]
        assert samples.downsample(_series(offsets_ms=[0, 1, 4, 10], heart_rate=[1.0] * 4), 2).offsets_ms == [2, 10]

    def test_a_pause_leaves_empty_buckets_that_are_dropped(self):
        series = _series(offsets_ms=[0, 1000, 2000, 100000], heart_rate=[10.0, 20.0, 30.0, 40.0])

        result = samples.downsample(series, 3)

        assert result.offsets_ms == [1000, 100000]
        assert result.heart_rate == [20.0, 40.0]

    def test_a_channel_is_averaged_over_the_samples_that_have_it_and_is_none_where_a_bucket_has_none(self):
        series = _series(
            offsets_ms=[0, 1000, 2000, 3000],
            heart_rate=[100.0, None, None, 140.0],
            power=[None, None, 300.0, 400.0],
        )

        result = samples.downsample(series, 2)

        assert result.heart_rate == [100.0, 140.0]
        assert result.power == [None, 350.0]

    def test_a_bucket_with_no_value_for_a_channel_is_none(self):
        series = _series(offsets_ms=[0, 1000, 2000, 3000], heart_rate=[100.0, 110.0, None, None])

        assert samples.downsample(series, 2).heart_rate == [105.0, None]

    def test_latitude_and_longitude_are_averaged_together_over_the_samples_that_have_both(self):
        series = _series(
            offsets_ms=[0, 1000, 2000, 3000],
            latitude=[10.0, 20.0, None, 40.0],
            longitude=[1.0, None, 3.0, 4.0],
        )

        result = samples.downsample(series, 2)

        assert result.latitude == [10.0, 40.0]
        assert result.longitude == [1.0, 4.0]

    def test_the_result_never_holds_more_than_the_bound(self):
        offsets = list(range(0, 100_000, 7))
        series = _series(offsets_ms=offsets, speed=[float(i % 5) for i in range(len(offsets))])

        for bound in (2, 3, 10, 999):
            result = samples.downsample(series, bound)
            assert len(result.offsets_ms) <= bound
            assert result.offsets_ms == sorted(result.offsets_ms)
            assert result.speed is not None
            assert len(result.speed) == len(result.offsets_ms)

    def test_samples_all_on_one_instant_collapse_to_one_sample(self):
        series = _series(offsets_ms=[500, 500, 500], heart_rate=[1.0, 2.0, 3.0])

        result = samples.downsample(series, 2)

        assert (result.offsets_ms, result.heart_rate) == ([500], [2.0])


class TestPace:
    def test_pace_is_the_reciprocal_of_a_speed_above_zero_and_none_elsewhere(self):
        assert samples.pace_from_speed([4.0, 0.0, None, 2.0, -1.0]) == [0.25, None, None, 0.5, None]
