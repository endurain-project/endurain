from unittest.mock import patch

from modules.activities.activity_streams.hr_zones import compute_hr_zone_breakdown_sync


def test_compute_hr_zone_percentages_with_even_distribution():
    waypoints = [
        {"hr": 100},
        {"hr": 130},
        {"hr": 150},
        {"hr": 170},
        {"hr": 190},
    ]

    result = compute_hr_zone_breakdown_sync(waypoints, max_heart_rate=200, total_timer_time=100)

    assert result is not None
    assert result["zone_1"] == {"percent": 20.0, "hr": "< 120", "time_seconds": 20}
    assert result["zone_2"] == {"percent": 20.0, "hr": "120 - 139", "time_seconds": 20}
    assert result["zone_3"] == {"percent": 20.0, "hr": "140 - 159", "time_seconds": 20}
    assert result["zone_4"] == {"percent": 20.0, "hr": "160 - 179", "time_seconds": 20}
    assert result["zone_5"] == {"percent": 20.0, "hr": ">= 180", "time_seconds": 20}


def test_compute_hr_zone_percentages_returns_none_for_empty_waypoints():
    assert compute_hr_zone_breakdown_sync([], max_heart_rate=200, total_timer_time=100) is None


def test_compute_hr_zone_percentages_returns_none_when_no_hr_values_exist():
    waypoints = [{"cadence": 90}, {"cadence": 95}]

    assert compute_hr_zone_breakdown_sync(waypoints, max_heart_rate=200, total_timer_time=100) is None


def test_compute_hr_zone_percentages_uses_zero_time_seconds_for_falsy_timer_time():
    waypoints = [{"hr": 100}, {"hr": 130}, {"hr": 150}, {"hr": 170}, {"hr": 190}]

    result = compute_hr_zone_breakdown_sync(waypoints, max_heart_rate=200, total_timer_time=0)

    assert result is not None
    assert all(zone["time_seconds"] == 0 for zone in result.values())


def test_compute_hr_zone_percentages_respects_known_zone_boundaries():
    waypoints = [
        {"hr": 119},
        {"hr": 120},
        {"hr": 139},
        {"hr": 140},
        {"hr": 159},
        {"hr": 160},
        {"hr": 179},
        {"hr": 180},
        {"hr": 199},
    ]

    result = compute_hr_zone_breakdown_sync(waypoints, max_heart_rate=200, total_timer_time=900)

    assert result is not None
    assert result["zone_1"]["percent"] == 11.11
    assert result["zone_2"]["percent"] == 22.22
    assert result["zone_3"]["percent"] == 22.22
    assert result["zone_4"]["percent"] == 22.22
    assert result["zone_5"]["percent"] == 22.22


def test_compute_hr_zone_breakdown_sync_matches_even_distribution():
    from modules.activities.activity_streams.hr_zones import compute_hr_zone_breakdown_sync

    waypoints = [{"hr": 100}, {"hr": 130}, {"hr": 150}, {"hr": 170}, {"hr": 190}]

    result = compute_hr_zone_breakdown_sync(waypoints, max_heart_rate=200, total_timer_time=100)

    assert result is not None
    assert result["zone_1"] == {"percent": 20.0, "hr": "< 120", "time_seconds": 20}
    assert result["zone_5"] == {"percent": 20.0, "hr": ">= 180", "time_seconds": 20}


def test_compute_hr_zone_breakdown_sync_returns_none_without_hr_values():
    from modules.activities.activity_streams.hr_zones import compute_hr_zone_breakdown_sync

    assert compute_hr_zone_breakdown_sync([{"cadence": 90}], max_heart_rate=200, total_timer_time=100) is None


class TestResolveMaxHeartRate:
    """``220 - age`` needs completed years, not a year subtraction."""

    def test_stored_value_wins(self):
        import modules.activities.activity_streams.hr_zones as hr_zones

        assert hr_zones.resolve_max_heart_rate(190, None, None) == 190

    def test_no_birthdate_and_no_stored_value(self):
        import modules.activities.activity_streams.hr_zones as hr_zones

        assert hr_zones.resolve_max_heart_rate(None, None, None) is None

    def test_birthday_not_yet_reached_this_year(self):
        """Subtracting birth years alone aged a December-born user a year early."""
        from datetime import date

        import modules.activities.activity_streams.hr_zones as hr_zones

        with patch.object(hr_zones.core_timezone, "today_in", return_value=date(2026, 3, 1)):
            result = hr_zones.resolve_max_heart_rate(None, date(1990, 12, 25), "UTC")

        # On 1 Mar 2026 a 1990-12-25 birthdate is 35, not 36.
        assert result == 220 - 35

    def test_birthday_already_passed_this_year(self):
        from datetime import date

        import modules.activities.activity_streams.hr_zones as hr_zones

        with patch.object(hr_zones.core_timezone, "today_in", return_value=date(2026, 3, 1)):
            result = hr_zones.resolve_max_heart_rate(None, date(1990, 1, 5), "UTC")

        assert result == 220 - 36

    def test_age_is_resolved_in_the_users_own_timezone(self):
        """A birthday is a local date: UTC would roll it a day early or late."""
        from datetime import date

        import modules.activities.activity_streams.hr_zones as hr_zones

        with patch.object(hr_zones.core_timezone, "today_in", return_value=date(2026, 3, 1)) as today_in:
            hr_zones.resolve_max_heart_rate(None, date(1990, 1, 5), "Pacific/Kiritimati")

        today_in.assert_called_once_with("Pacific/Kiritimati")

    def test_falls_back_to_the_server_timezone_when_the_user_has_none(self):
        """``users.timezone`` is nullable for accounts predating the setting."""
        from datetime import date

        import core.config as core_config
        import modules.activities.activity_streams.hr_zones as hr_zones

        with patch.object(hr_zones.core_timezone, "today_in", return_value=date(2026, 3, 1)) as today_in:
            hr_zones.resolve_max_heart_rate(None, date(1990, 1, 5), None)

        today_in.assert_called_once_with(core_config.settings.TZ)
