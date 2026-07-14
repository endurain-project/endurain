"""Utility functions for activity stream data."""

import datetime
from typing import overload

import numpy as np
from fastapi.concurrency import run_in_threadpool

import activities.activity.schema as activity_schema
import activities.activity_streams.constants as activity_streams_constants
import activities.activity_streams.models as activity_streams_models
import activities.activity_streams.schema as activity_streams_schema
import users.users.schema as users_schema

# Map stream type to activity hide attribute
_STREAM_HIDE_MAP: dict[int, str] = {
    activity_streams_constants.STREAM_TYPE_HR: "hide_hr",
    activity_streams_constants.STREAM_TYPE_POWER: "hide_power",
    activity_streams_constants.STREAM_TYPE_CADENCE: "hide_cadence",
    activity_streams_constants.STREAM_TYPE_ELEVATION: "hide_elevation",
    activity_streams_constants.STREAM_TYPE_SPEED: "hide_speed",
    activity_streams_constants.STREAM_TYPE_PACE: "hide_pace",
    activity_streams_constants.STREAM_TYPE_MAP: "hide_map",
}

_DEFAULT_MAX_HEART_RATE: int = 220
_HR_ZONE_1_PERCENT: float = 0.6
_HR_ZONE_2_PERCENT: float = 0.7
_HR_ZONE_3_PERCENT: float = 0.8
_HR_ZONE_4_PERCENT: float = 0.9


def is_stream_hidden(
    activity: activity_schema.Activity,
    stream_type: int,
) -> bool:
    """
    Check if a stream type is hidden.

    Args:
        activity: The activity schema instance.
        stream_type: The stream type constant.

    Returns:
        True if the stream should be hidden.
    """
    attr = _STREAM_HIDE_MAP.get(stream_type)
    return bool(attr and getattr(activity, attr, False))


def filter_visible_streams(
    streams: list[activity_streams_models.ActivityStreams],
    activity: activity_schema.Activity,
) -> list[activity_streams_models.ActivityStreams]:
    """
    Filter out streams hidden by the activity.

    Args:
        streams: List of stream ORM instances.
        activity: The activity schema instance.

    Returns:
        Streams that are not hidden.
    """
    return [s for s in streams if not is_stream_hidden(activity, s.stream_type)]


@overload
def transform_activity_streams(
    activity_streams: list[activity_streams_models.ActivityStreams],
) -> list[activity_streams_schema.ActivityStreamsRead]: ...


@overload
def transform_activity_streams(
    activity_streams: activity_streams_models.ActivityStreams,
) -> activity_streams_schema.ActivityStreamsRead: ...


def transform_activity_streams(
    activity_streams: activity_streams_models.ActivityStreams | list[activity_streams_models.ActivityStreams],
) -> activity_streams_schema.ActivityStreamsRead | list[activity_streams_schema.ActivityStreamsRead]:
    """
    Transform a stream or list of streams to a Pydantic schema or list of schemas.

    Args:
        activity_streams: The stream ORM instance or list of stream ORM instances.

    Returns:
        The activity stream as a schema or list of schemas.
    """
    if isinstance(activity_streams, list):
        return [activity_streams_schema.ActivityStreamsRead.model_validate(stream) for stream in activity_streams]
    return activity_streams_schema.ActivityStreamsRead.model_validate(activity_streams)


def resolve_max_heart_rate(user: users_schema.UsersRead) -> int | None:
    """
    Resolve a user's max heart rate.

    Args:
        user: The user ORM instance (must expose max_heart_rate and birthdate).

    Returns:
        The stored max HR, the age-derived value (220 - age), or None.
    """
    if user.max_heart_rate:
        return user.max_heart_rate
    if user.birthdate:
        current_year = datetime.datetime.now(datetime.UTC).year
        return _DEFAULT_MAX_HEART_RATE - (current_year - user.birthdate.year)
    return None


def compute_hr_zone_breakdown_sync(
    waypoints: list[dict],
    max_heart_rate: int,
    total_timer_time: float | None,
) -> dict | None:
    """
    Compute the HR zone breakdown for a set of waypoints.

    Args:
        waypoints: List of waypoint dicts (each may contain an "hr" key).
        max_heart_rate: The user's max heart rate.
        total_timer_time: Activity total timer time in seconds (may be falsy).

    Returns:
        A dict of zone_1..zone_5 entries, or None if it cannot be computed.
    """

    if not waypoints or not isinstance(waypoints, list):
        return None

    zone_1 = max_heart_rate * _HR_ZONE_1_PERCENT
    zone_2 = max_heart_rate * _HR_ZONE_2_PERCENT
    zone_3 = max_heart_rate * _HR_ZONE_3_PERCENT
    zone_4 = max_heart_rate * _HR_ZONE_4_PERCENT

    def _compute_zone_counts(
        waypoints: list[dict],
        zone_1: float,
        zone_2: float,
        zone_3: float,
        zone_4: float,
    ) -> list[float] | None:
        """
        Compute per-zone percentage counts from waypoints.

        Args:
            waypoints: List of waypoint dicts with optional "hr" key.
            zone_1: Upper bound of zone 1.
            zone_2: Upper bound of zone 2.
            zone_3: Upper bound of zone 3.
            zone_4: Upper bound of zone 4.

        Returns:
            List of five zone percentages (0-100), or None if no
            HR data is present.
        """
        hr_values = np.array([float(hr) for wp in waypoints if (hr := wp.get("hr")) is not None])
        total = len(hr_values)
        if total == 0:
            return None

        zone_counts = [
            np.sum(hr_values < zone_1),
            np.sum((hr_values >= zone_1) & (hr_values < zone_2)),
            np.sum((hr_values >= zone_2) & (hr_values < zone_3)),
            np.sum((hr_values >= zone_3) & (hr_values < zone_4)),
            np.sum(hr_values >= zone_4),
        ]
        return [round((count / total) * 100, 2) for count in zone_counts]

    zone_percentages: list[float] | None = _compute_zone_counts(waypoints, zone_1, zone_2, zone_3, zone_4)

    if zone_percentages is None:
        return None

    if total_timer_time:
        zone_time_seconds = [int((percent / 100) * float(total_timer_time)) for percent in zone_percentages]
    else:
        zone_time_seconds = [0, 0, 0, 0, 0]

    zone_hr = {
        "zone_1": f"< {int(zone_1)}",
        "zone_2": f"{int(zone_1)} - {int(zone_2) - 1}",
        "zone_3": f"{int(zone_2)} - {int(zone_3) - 1}",
        "zone_4": f"{int(zone_3)} - {int(zone_4) - 1}",
        "zone_5": f">= {int(zone_4)}",
    }

    return {
        "zone_1": {"percent": zone_percentages[0], "hr": zone_hr["zone_1"], "time_seconds": zone_time_seconds[0]},
        "zone_2": {"percent": zone_percentages[1], "hr": zone_hr["zone_2"], "time_seconds": zone_time_seconds[1]},
        "zone_3": {"percent": zone_percentages[2], "hr": zone_hr["zone_3"], "time_seconds": zone_time_seconds[2]},
        "zone_4": {"percent": zone_percentages[3], "hr": zone_hr["zone_4"], "time_seconds": zone_time_seconds[3]},
        "zone_5": {"percent": zone_percentages[4], "hr": zone_hr["zone_5"], "time_seconds": zone_time_seconds[4]},
    }


async def compute_hr_zone_breakdown(
    waypoints: list[dict],
    max_heart_rate: int,
    total_timer_time: float | None,
) -> dict | None:
    """
    Compute the HR zone breakdown off the event loop.

    Args:
        waypoints: List of waypoint dicts (each may contain an "hr" key).
        max_heart_rate: The user's max heart rate.
        total_timer_time: Activity total timer time in seconds (may be falsy).

    Returns:
        A dict of zone_1..zone_5 entries, or None if it cannot be computed.
    """
    return await run_in_threadpool(compute_hr_zone_breakdown_sync, waypoints, max_heart_rate, total_timer_time)


async def build_zone_percentages(
    user: users_schema.UsersRead, activity: activity_schema.Activity, waypoints: list[dict]
) -> dict[str, dict] | None:
    """
    Build the metric-keyed zone_percentages payload for a stream.

    Args:
        user: The user ORM instance.
        activity: The activity schema instance.
        waypoints: The HR stream waypoints.

    Returns:
        {"hr": {...}} when HR zones can be computed, otherwise None.
    """
    max_heart_rate = resolve_max_heart_rate(user)
    if not max_heart_rate:
        return None
    total_timer_time = activity.total_timer_time
    hr_block: dict | None = await compute_hr_zone_breakdown(waypoints, max_heart_rate, total_timer_time)
    if hr_block is None:
        return None
    return {"hr": hr_block}
