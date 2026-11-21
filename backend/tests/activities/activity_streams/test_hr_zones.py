"""Heart-rate zone maths and the max heart rate it is derived from."""

from datetime import UTC, date, datetime

import jasil.runtime as platform_runtime
import pytest

import core.config as core_config
import modules.activities.activity_streams.hr_zones as hr_zones

_EVEN = [{"hr": 100}, {"hr": 130}, {"hr": 150}, {"hr": 170}, {"hr": 190}]


class TestZoneBreakdown:
    def test_samples_spread_over_the_zones_split_the_timer_time_evenly(self):
        result = hr_zones.compute_hr_zone_breakdown_sync(_EVEN, max_heart_rate=200, total_timer_time=100)

        assert result == {
            "zone_1": {"percent": 20.0, "hr": "< 120", "time_seconds": 20},
            "zone_2": {"percent": 20.0, "hr": "120 - 139", "time_seconds": 20},
            "zone_3": {"percent": 20.0, "hr": "140 - 159", "time_seconds": 20},
            "zone_4": {"percent": 20.0, "hr": "160 - 179", "time_seconds": 20},
            "zone_5": {"percent": 20.0, "hr": ">= 180", "time_seconds": 20},
        }

    def test_a_sample_on_a_boundary_belongs_to_the_zone_above_it(self):
        waypoints = [{"hr": hr} for hr in (119, 120, 139, 140, 159, 160, 179, 180, 199)]

        result = hr_zones.compute_hr_zone_breakdown_sync(waypoints, max_heart_rate=200, total_timer_time=900)

        assert result is not None
        assert [result[f"zone_{n}"]["percent"] for n in range(1, 6)] == [11.11, 22.22, 22.22, 22.22, 22.22]

    def test_a_zero_or_missing_timer_time_gives_zero_seconds_in_every_zone(self):
        for timer_time in (0, None):
            result = hr_zones.compute_hr_zone_breakdown_sync(_EVEN, max_heart_rate=200, total_timer_time=timer_time)

            assert result is not None
            assert all(zone["time_seconds"] == 0 for zone in result.values())

    def test_samples_without_a_heart_rate_are_left_out_of_the_shares(self):
        waypoints = [{"hr": 100}, {"hr": None}, {"cad": 90}, {"hr": 190}]

        result = hr_zones.compute_hr_zone_breakdown_sync(waypoints, max_heart_rate=200, total_timer_time=100)

        assert result is not None
        assert (result["zone_1"]["percent"], result["zone_5"]["percent"], result["zone_3"]["percent"]) == (
            50.0,
            50.0,
            0.0,
        )

    @pytest.mark.parametrize("waypoints", [[], [{"cad": 90}, {"cad": 95}], [{"hr": None}]])
    def test_no_heart_rate_samples_give_no_breakdown(self, waypoints):
        assert hr_zones.compute_hr_zone_breakdown_sync(waypoints, max_heart_rate=200, total_timer_time=100) is None


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
