from jasil.backends.state_memory import MemoryState

import modules.garmin.rate_limit_store as garmin_rate_limit_store


def make_garmin_activity(
    activity_id: int = 1,
    activity_name: str = "Morning Run",
    activity_type: dict | None = None,
    duration: float = 3600.0,
    distance: float = 10000.0,
    elevation_gain: float = 50.0,
    start_time_gmt: str = "2024-01-15 08:00:00",
):
    if activity_type is None:
        activity_type = {"typeId": 1, "typeKey": "running", "parentTypeId": 17}
    return {
        "activityId": activity_id,
        "activityName": activity_name,
        "activityType": activity_type,
        "duration": duration,
        "distance": distance,
        "elevationGain": elevation_gain,
        "startTimeGMT": start_time_gmt,
        "averageHeartRate": 145,
        "maxHeartRate": 175,
        "averageSpeed": 2.78,
        "maxSpeed": 5.0,
        "calories": 500,
    }


def make_garmin_gear(gear_id: str = "g12345", display_name: str = "Nike Pegasus"):
    return {
        "uuid": gear_id,
        "displayName": display_name,
        "distance": 500000.0,
    }


def rate_limits() -> garmin_rate_limit_store.GarminRateLimitStore:
    """Return a rate-limit store over fresh state, so a limit one test records never reaches another."""
    return garmin_rate_limit_store.GarminRateLimitStore(MemoryState())
