"""Heart-rate zone maths and the max heart rate it is derived from."""

from datetime import UTC, date, datetime

import jasil.runtime as platform_runtime
import pytest

import core.config as core_config
import modules.activities.activity_streams.hr_zones as hr_zones


def _series(*samples: tuple[float, int | None]) -> tuple[list[int], list[int | None]]:
    """Build ``(offsets_ms, heart_rate)`` from ``(seconds from the start, hr)`` pairs."""
    return [round(seconds * 1000) for seconds, _ in samples], [hr for _, hr in samples]


def _zones(series, max_heart_rate=200):
    offsets_ms, heart_rate = series
    return hr_zones.compute_hr_zone_breakdown_sync(offsets_ms, heart_rate, max_heart_rate)


def _seconds(result) -> list[int]:
    return [result[f"zone_{n}"]["time_seconds"] for n in range(1, 6)]


def _percents(result) -> list[float]:
    return [result[f"zone_{n}"]["percent"] for n in range(1, 6)]


_EVEN = _series((0, 100), (1, 130), (2, 150), (3, 170), (4, 190), (5, 190))


class TestZoneBreakdown:
    def test_samples_one_second_apart_split_the_time_by_the_seconds_each_is_held(self):
        result = _zones(_EVEN)

        assert result == {
            "zone_1": {"percent": 20.0, "hr": "< 120", "time_seconds": 1},
            "zone_2": {"percent": 20.0, "hr": "120 - 139", "time_seconds": 1},
            "zone_3": {"percent": 20.0, "hr": "140 - 159", "time_seconds": 1},
            "zone_4": {"percent": 20.0, "hr": "160 - 179", "time_seconds": 1},
            "zone_5": {"percent": 20.0, "hr": ">= 180", "time_seconds": 1},
        }

    def test_a_sample_on_a_boundary_belongs_to_the_zone_above_it(self):
        hrs = (119, 120, 139, 140, 159, 160, 179, 180, 199, 199)

        result = _zones(_series(*enumerate(hrs)))

        assert result is not None
        assert _percents(result) == [11.11, 22.22, 22.22, 22.22, 22.22]

    def test_smart_recording_counts_the_time_a_value_is_held_not_the_samples(self):
        # 150 bpm is held 10 s by one sample, then ten 1 Hz samples of 120 bpm: by count zone 3 would be 1/11.
        result = _zones(_series((0, 150), *[(10 + i, 120) for i in range(11)]))

        assert result is not None
        assert _seconds(result) == [0, 10, 10, 0, 0]
        assert _percents(result) == [0.0, 50.0, 50.0, 0.0, 0.0]

    def test_a_heart_rate_of_zero_is_a_dropout_that_adds_no_time_and_is_not_zone_1(self):
        result = _zones(_series((0, 150), (1, 0), (2, 0), (3, 150), (4, 150)))

        assert result is not None
        assert _seconds(result) == [0, 0, 4, 0, 0]
        assert _percents(result) == [0.0, 0.0, 100.0, 0.0, 0.0]

    def test_a_pause_adds_at_most_the_pause_threshold_to_the_zone_before_it(self):
        # 1 Hz sampling gives a 15 s threshold: the 300 s gap after t=4 holds 15 s, not 300.
        series = _series(*[(i, 150) for i in range(5)], (304, 120), (305, 120), (306, 120))

        result = _zones(series)

        assert result is not None
        assert _seconds(result) == [0, 2, 19, 0, 0]

    def test_the_pause_threshold_follows_the_heart_rate_samples_not_the_other_channels(self):
        # Heart rate every 10 s gives a 30 s threshold, so the 25 s gap after t=30 is held whole; the 1 Hz samples
        # of the other channels in between (no heart rate) would give 15 s.
        heart_rate = {0: 150, 10: 150, 20: 150, 30: 150, 55: 120, 65: 120}
        series = _series(*[(second, heart_rate.get(second)) for second in range(66)])

        result = _zones(series)

        assert result is not None
        assert _seconds(result) == [0, 10, 55, 0, 0]

    def test_samples_on_one_instant_share_that_instant(self):
        result = _zones(_series((0, 150), (0, 170), (2, 120)))

        assert result is not None
        assert _seconds(result) == [0, 0, 1, 1, 0]
        assert _percents(result) == [0.0, 0.0, 50.0, 50.0, 0.0]

    def test_the_percentages_sum_to_a_hundred_and_the_seconds_to_the_held_time(self):
        result = _zones(_series((0, 100), (1, 130), (2, 150), (3, 150)))

        assert result is not None
        assert sum(_percents(result)) == pytest.approx(100.0, abs=0.02)
        assert sum(_seconds(result)) == 3

    def test_samples_without_a_heart_rate_are_left_out_with_their_time(self):
        result = _zones(_series((0, 100), (1, None), (2, None), (3, 190), (4, 190)))

        assert result is not None
        assert _seconds(result) == [3, 0, 0, 0, 1]

    def test_sub_second_offsets_are_held_by_their_milliseconds(self):
        result = _zones(([0, 500, 1000], [150, 120, 120]))

        assert result is not None
        assert _percents(result) == [0.0, 50.0, 50.0, 0.0, 0.0]

    def test_a_series_stamped_in_seconds_from_the_start_is_held_by_those_seconds(self):
        result = _zones(_series((0, 150), (10, 120), (11, 120)))

        assert result is not None
        assert _seconds(result) == [0, 1, 10, 0, 0]

    @pytest.mark.parametrize(
        "series",
        [
            ([], []),
            ([0, 1000], [None, None]),
            ([0], [None]),
            _series((0, 0), (1, 0), (2, 0)),
            _series((0, 150)),
            _series((5, 150), (5, 170)),
        ],
        ids=["empty", "no-hr", "none", "all-zero", "one-sample", "one-instant"],
    )
    def test_a_series_that_holds_no_time_in_a_zone_gives_no_breakdown(self, series):
        assert _zones(series) is None


@pytest.fixture
def clock(db):
    """The platform's fixed clock, which the real-database harness installs, so a test can choose the day."""
    return platform_runtime.get_active_platform().clock


class TestResolveMaxHeartRate:
    def test_a_stored_value_wins_over_the_birthdate(self):
        assert hr_zones.resolve_max_heart_rate(190, date(1990, 1, 5), "UTC") == 190

    def test_no_birthdate_and_no_stored_value_gives_none(self):
        assert hr_zones.resolve_max_heart_rate(None, None, None) is None

    def test_a_birthday_not_yet_reached_this_year_counts_the_previous_age(self, clock):
        clock.moment = datetime(2026, 3, 1, 12, tzinfo=UTC)

        assert hr_zones.resolve_max_heart_rate(None, date(1990, 12, 25), "UTC") == 220 - 35

    def test_a_birthday_already_passed_this_year_counts_the_new_age(self, clock):
        clock.moment = datetime(2026, 3, 1, 12, tzinfo=UTC)

        assert hr_zones.resolve_max_heart_rate(None, date(1990, 1, 5), "UTC") == 220 - 36

    def test_the_age_is_counted_on_the_users_own_calendar_day(self, clock):
        clock.moment = datetime(2026, 3, 1, 23, tzinfo=UTC)
        birthdate = date(1990, 3, 2)

        assert hr_zones.resolve_max_heart_rate(None, birthdate, "UTC") == 220 - 35
        assert hr_zones.resolve_max_heart_rate(None, birthdate, "Pacific/Kiritimati") == 220 - 36

    def test_a_user_without_a_timezone_is_aged_on_the_servers_calendar_day(self, clock):
        clock.moment = datetime(2026, 3, 1, 23, tzinfo=UTC)
        birthdate = date(1990, 3, 2)

        assert hr_zones.resolve_max_heart_rate(None, birthdate, None) == hr_zones.resolve_max_heart_rate(
            None, birthdate, core_config.settings.TZ
        )
