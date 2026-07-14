from activities.activity_streams.utils import compute_hr_zone_breakdown


async def test_compute_hr_zone_percentages_with_even_distribution():
    waypoints = [
        {"hr": 100},
        {"hr": 130},
        {"hr": 150},
        {"hr": 170},
        {"hr": 190},
    ]

    result = await compute_hr_zone_breakdown(waypoints, max_heart_rate=200, total_timer_time=100)

    assert result is not None
    assert result["zone_1"] == {"percent": 20.0, "hr": "< 120", "time_seconds": 20}
    assert result["zone_2"] == {"percent": 20.0, "hr": "120 - 139", "time_seconds": 20}
    assert result["zone_3"] == {"percent": 20.0, "hr": "140 - 159", "time_seconds": 20}
    assert result["zone_4"] == {"percent": 20.0, "hr": "160 - 179", "time_seconds": 20}
    assert result["zone_5"] == {"percent": 20.0, "hr": ">= 180", "time_seconds": 20}


async def test_compute_hr_zone_percentages_returns_none_for_empty_waypoints():
    assert await compute_hr_zone_breakdown([], max_heart_rate=200, total_timer_time=100) is None


async def test_compute_hr_zone_percentages_returns_none_when_no_hr_values_exist():
    waypoints = [{"cadence": 90}, {"cadence": 95}]

    assert await compute_hr_zone_breakdown(waypoints, max_heart_rate=200, total_timer_time=100) is None


async def test_compute_hr_zone_percentages_uses_zero_time_seconds_for_falsy_timer_time():
    waypoints = [{"hr": 100}, {"hr": 130}, {"hr": 150}, {"hr": 170}, {"hr": 190}]

    result = await compute_hr_zone_breakdown(waypoints, max_heart_rate=200, total_timer_time=0)

    assert result is not None
    assert all(zone["time_seconds"] == 0 for zone in result.values())


async def test_compute_hr_zone_percentages_respects_known_zone_boundaries():
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

    result = await compute_hr_zone_breakdown(waypoints, max_heart_rate=200, total_timer_time=900)

    assert result is not None
    assert result["zone_1"]["percent"] == 11.11
    assert result["zone_2"]["percent"] == 22.22
    assert result["zone_3"]["percent"] == 22.22
    assert result["zone_4"]["percent"] == 22.22
    assert result["zone_5"]["percent"] == 22.22


def test_compute_hr_zone_breakdown_sync_matches_even_distribution():
    from activities.activity_streams.utils import compute_hr_zone_breakdown_sync

    waypoints = [{"hr": 100}, {"hr": 130}, {"hr": 150}, {"hr": 170}, {"hr": 190}]

    result = compute_hr_zone_breakdown_sync(waypoints, max_heart_rate=200, total_timer_time=100)

    assert result is not None
    assert result["zone_1"] == {"percent": 20.0, "hr": "< 120", "time_seconds": 20}
    assert result["zone_5"] == {"percent": 20.0, "hr": ">= 180", "time_seconds": 20}


def test_compute_hr_zone_breakdown_sync_returns_none_without_hr_values():
    from activities.activity_streams.utils import compute_hr_zone_breakdown_sync

    assert compute_hr_zone_breakdown_sync([{"cadence": 90}], max_heart_rate=200, total_timer_time=100) is None
