"""Shared utilities for activity file import normalization."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from geopy.distance import geodesic
from timezonefinder import TimezoneFinder

import activities.activity.schema as activities_schema
import users.users_privacy_settings.models as users_privacy_settings_models
import users.users_privacy_settings.utils as users_privacy_settings_utils

# ISO 8601 datetime format used throughout the import pipeline
_DT_FMT = "%Y-%m-%dT%H:%M:%S"

# Canonical keys present in every activity file payload's waypoint streams.
# Used as documentation and for IDE hint support.
STREAM_KEYS: tuple[str, ...] = (
    "is_elevation_set",
    "ele_waypoints",
    "is_power_set",
    "power_waypoints",
    "is_heart_rate_set",
    "hr_waypoints",
    "is_velocity_set",
    "vel_waypoints",
    "pace_waypoints",
    "is_cadence_set",
    "cad_waypoints",
    "is_lat_lon_set",
    "lat_lon_waypoints",
)


def build_activity_privacy_kwargs(
    user_privacy_settings: users_privacy_settings_models.UsersPrivacySettings,
) -> dict[str, bool | int]:
    """Build privacy field kwargs for Activity schema from ORM model.

    Args:
        user_privacy_settings: The ORM privacy-settings record for the
            activity owner.

    Returns:
        A dict with all 16 privacy fields ready to unpack into an
        Activity constructor call.
    """
    ups = user_privacy_settings
    return {
        "visibility": users_privacy_settings_utils.visibility_to_int(ups.default_activity_visibility),
        "hide_start_time": ups.hide_activity_start_time or False,
        "hide_location": ups.hide_activity_location or False,
        "hide_map": ups.hide_activity_map or False,
        "hide_hr": ups.hide_activity_hr or False,
        "hide_power": ups.hide_activity_power or False,
        "hide_cadence": ups.hide_activity_cadence or False,
        "hide_elevation": ups.hide_activity_elevation or False,
        "hide_speed": ups.hide_activity_speed or False,
        "hide_pace": ups.hide_activity_pace or False,
        "hide_laps": ups.hide_activity_laps or False,
        "hide_workout_sets_steps": (ups.hide_activity_workout_sets_steps or False),
        "hide_gear": ups.hide_activity_gear or False,
    }


def build_activity_file_payload(
    activity: activities_schema.Activity,
    waypoints: dict[str, list[dict]],
    laps: list[dict],
    extras: dict | None = None,
) -> dict:
    """Build normalized activity file import payload.

    Args:
        activity: Populated Activity schema instance.
        waypoints: Dict keyed by stream name (e.g. ``'lat_lon_waypoints'``,
            ``'ele_waypoints'``, …) mapping to lists of waypoint dicts.
        laps: List of lap dicts for the activity.
        extras: Optional format-specific extras (e.g. FIT sets /
            workout_steps).

    Returns:
        A dict containing the activity, all stream flags/lists, laps, and
        any extras — matching the structure expected by
        ``activities/activity/utils.py`` callers.
    """
    payload: dict = {
        "activity": activity,
        "is_elevation_set": bool(waypoints.get("ele_waypoints")),
        "ele_waypoints": waypoints.get("ele_waypoints", []),
        "is_power_set": bool(waypoints.get("power_waypoints")),
        "power_waypoints": waypoints.get("power_waypoints", []),
        "is_heart_rate_set": bool(waypoints.get("hr_waypoints")),
        "hr_waypoints": waypoints.get("hr_waypoints", []),
        "is_velocity_set": bool(waypoints.get("vel_waypoints")),
        "vel_waypoints": waypoints.get("vel_waypoints", []),
        "pace_waypoints": waypoints.get("pace_waypoints", []),
        "is_cadence_set": bool(waypoints.get("cad_waypoints")),
        "cad_waypoints": waypoints.get("cad_waypoints", []),
        "is_lat_lon_set": bool(waypoints.get("lat_lon_waypoints")),
        "lat_lon_waypoints": waypoints.get("lat_lon_waypoints", []),
        "is_temperature_set": bool(waypoints.get("temp_waypoints")),
        "temp_waypoints": waypoints.get("temp_waypoints", []),
        "laps": laps,
    }
    if extras:
        payload.update(extras)
    return payload


class LapMetrics(TypedDict):
    """Typed dictionary for a single lap's metrics.

    Attributes:
        start_time: ISO timestamp of lap start.
        start_position_lat: Latitude of lap start.
        start_position_long: Longitude of lap start.
        end_position_lat: Latitude of lap end.
        end_position_long: Longitude of lap end.
        total_elapsed_time: Elapsed seconds.
        total_timer_time: Timer seconds.
        total_distance: Distance in metres.
        avg_heart_rate: Average HR in bpm.
        max_heart_rate: Maximum HR in bpm.
        avg_cadence: Average cadence.
        max_cadence: Maximum cadence.
        avg_power: Average power in watts.
        max_power: Maximum power in watts.
        total_ascent: Total ascent in metres.
        total_descent: Total descent in metres.
        normalized_power: Normalized power.
        enhanced_avg_pace: Average pace (min/km).
        enhanced_avg_speed: Average speed (m/s).
        enhanced_max_pace: Maximum pace (min/km).
        enhanced_max_speed: Maximum speed (m/s).
    """

    start_time: str
    start_position_lat: float | None
    start_position_long: float | None
    end_position_lat: float | None
    end_position_long: float | None
    total_elapsed_time: float
    total_timer_time: float
    total_distance: float
    avg_heart_rate: int | None
    max_heart_rate: int | None
    avg_cadence: int | None
    max_cadence: int | None
    avg_power: int | None
    max_power: int | None
    total_ascent: int | None
    total_descent: int | None
    normalized_power: int | None
    enhanced_avg_pace: float | None
    enhanced_avg_speed: float | None
    enhanced_max_pace: float | None
    enhanced_max_speed: float | None


def filter_waypoints_by_time_range(
    waypoints: list[dict],
    start_time: str,
    end_time: str,
) -> list[dict]:
    """Return waypoints whose time falls within [start_time, end_time].

    Args:
        waypoints: List of waypoint dicts each containing a ``'time'``
            key with an ISO 8601 string.
        start_time: ISO 8601 start time string (inclusive).
        end_time: ISO 8601 end time string (inclusive).

    Returns:
        Filtered list of waypoint dicts.
    """
    start_dt = datetime.strptime(start_time, _DT_FMT)
    end_dt = datetime.strptime(end_time, _DT_FMT)
    return [wp for wp in waypoints if start_dt <= datetime.strptime(wp["time"], _DT_FMT) <= end_dt]


def _compute_lap_metrics(
    start_time: str,
    end_time: str,
    start_point: dict,
    end_point: dict,
    total_distance: float,
    ele_waypoints: list[dict],
    power_waypoints: list[dict],
    hr_waypoints: list[dict],
    cad_waypoints: list[dict],
    vel_waypoints: list[dict],
) -> LapMetrics:
    """Compute metrics for a single activity lap.

    Args:
        start_time: ISO timestamp of lap start.
        end_time: ISO timestamp of lap end.
        start_point: Lat/lon dict of lap start.
        end_point: Lat/lon dict of lap end.
        total_distance: Lap distance in km.
        ele_waypoints: Full elevation stream.
        power_waypoints: Full power stream.
        hr_waypoints: Full HR stream.
        cad_waypoints: Full cadence stream.
        vel_waypoints: Full velocity stream.

    Returns:
        Dict with all computed lap metrics.
    """
    # Imported lazily to avoid a circular import: activities.activity.utils
    # imports utils_gpx, which re-exports names from this module.
    import activities.activity.utils as activities_utils

    lap_ele = filter_waypoints_by_time_range(
        ele_waypoints,
        start_time,
        end_time,
    )
    lap_power = filter_waypoints_by_time_range(
        power_waypoints,
        start_time,
        end_time,
    )
    lap_hr = filter_waypoints_by_time_range(
        hr_waypoints,
        start_time,
        end_time,
    )
    lap_cad = filter_waypoints_by_time_range(
        cad_waypoints,
        start_time,
        end_time,
    )
    lap_vel = filter_waypoints_by_time_range(
        vel_waypoints,
        start_time,
        end_time,
    )

    ele_gain, ele_loss = None, None
    if lap_ele:
        ele_gain, ele_loss = activities_utils.compute_elevation_gain_and_loss(
            elevations=lap_ele,
        )

    avg_hr, max_hr = None, None
    if lap_hr:
        avg_hr, max_hr = activities_utils.calculate_avg_and_max(
            lap_hr,
            "hr",
        )

    avg_cad, max_cad = None, None
    if lap_cad:
        avg_cad, max_cad = activities_utils.calculate_avg_and_max(
            lap_cad,
            "cad",
        )

    avg_speed, max_speed = None, None
    if lap_vel:
        avg_speed, max_speed = activities_utils.calculate_avg_and_max(
            lap_vel,
            "vel",
        )

    avg_power, max_power, norm_power = None, None, None
    if lap_power:
        avg_power, max_power = activities_utils.calculate_avg_and_max(
            lap_power,
            "power",
        )
        norm_power = activities_utils.calculate_np(lap_power)

    elapsed = (datetime.strptime(end_time, _DT_FMT) - datetime.strptime(start_time, _DT_FMT)).total_seconds()

    return {
        "start_time": start_time,
        "start_position_lat": start_point["lat"],
        "start_position_long": start_point["lon"],
        "end_position_lat": end_point["lat"],
        "end_position_long": end_point["lon"],
        "total_elapsed_time": elapsed,
        "total_timer_time": elapsed,
        "total_distance": total_distance * 1000,
        "avg_heart_rate": round(avg_hr) if avg_hr else None,
        "max_heart_rate": round(max_hr) if max_hr else None,
        "avg_cadence": round(avg_cad) if avg_cad else None,
        "max_cadence": round(max_cad) if max_cad else None,
        "avg_power": round(avg_power) if avg_power else None,
        "max_power": round(max_power) if max_power else None,
        "total_ascent": round(ele_gain) if ele_gain else None,
        "total_descent": round(ele_loss) if ele_loss else None,
        "normalized_power": round(norm_power) if norm_power else None,
        "enhanced_avg_pace": 1 / avg_speed if avg_speed else None,
        "enhanced_avg_speed": avg_speed,
        "enhanced_max_pace": 1 / max_speed if max_speed else None,
        "enhanced_max_speed": max_speed,
    }


def generate_activity_laps(
    lat_lon_waypoints: list[dict],
    ele_waypoints: list[dict],
    power_waypoints: list[dict],
    hr_waypoints: list[dict],
    cad_waypoints: list[dict],
    vel_waypoints: list[dict],
    distance_per_lap_km: float = 1.0,
) -> list[LapMetrics]:
    """Split waypoints into distance-based laps and compute metrics.

    Args:
        lat_lon_waypoints: List of lat/lon dicts.
        ele_waypoints: List of elevation dicts.
        power_waypoints: List of power dicts.
        hr_waypoints: List of heart rate dicts.
        cad_waypoints: List of cadence dicts.
        vel_waypoints: List of velocity dicts.
        distance_per_lap_km: Km per lap (default 1.0).

    Returns:
        List of lap dicts with computed metrics.
    """
    laps: list[LapMetrics] = []
    current_lap_distance = 0.0
    lap_start = None

    for i in range(1, len(lat_lon_waypoints)):
        prev_point = lat_lon_waypoints[i - 1]
        current_point = lat_lon_waypoints[i]

        segment_distance = geodesic(
            (prev_point["lat"], prev_point["lon"]),
            (current_point["lat"], current_point["lon"]),
        ).kilometers

        current_lap_distance += segment_distance

        if lap_start is None:
            lap_start = prev_point

        if current_lap_distance >= distance_per_lap_km:
            laps.append(
                _compute_lap_metrics(
                    start_time=lap_start["time"],
                    end_time=current_point["time"],
                    start_point=lap_start,
                    end_point=current_point,
                    total_distance=current_lap_distance,
                    ele_waypoints=ele_waypoints,
                    power_waypoints=power_waypoints,
                    hr_waypoints=hr_waypoints,
                    cad_waypoints=cad_waypoints,
                    vel_waypoints=vel_waypoints,
                )
            )
            lap_start = current_point
            current_lap_distance = 0.0

    if lap_start is not None and current_lap_distance > 0:
        laps.append(
            _compute_lap_metrics(
                start_time=lap_start["time"],
                end_time=lat_lon_waypoints[-1]["time"],
                start_point=lap_start,
                end_point=lat_lon_waypoints[-1],
                total_distance=current_lap_distance,
                ele_waypoints=ele_waypoints,
                power_waypoints=power_waypoints,
                hr_waypoints=hr_waypoints,
                cad_waypoints=cad_waypoints,
                vel_waypoints=vel_waypoints,
            )
        )

    return laps


def filter_streams_by_time_range(
    streams: dict[str, list[dict]],
    start_time: datetime,
    end_time: datetime,
) -> dict[str, list[dict]]:
    """Filter all waypoint streams to a time range.

    Handles both tz-naive and tz-aware ``start_time`` / ``end_time``.
    Waypoint ``'time'`` values are parsed as ISO 8601 strings and treated
    as UTC when no timezone info is present.

    Args:
        streams: Dict keyed by stream name mapping to lists of waypoint
            dicts, each containing a ``'time'`` key.
        start_time: Inclusive lower bound (tz-aware or tz-naive UTC).
        end_time: Inclusive upper bound (tz-aware or tz-naive UTC).

    Returns:
        New dict with the same keys, each stream filtered to the given
        time range.
    """
    # Normalise bounds to UTC-aware for consistent comparisons.
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=UTC)

    def _parse_wp_time(time_str: str) -> datetime:
        dt = datetime.strptime(time_str, _DT_FMT)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt

    return {
        key: [wp for wp in waypoints if start_time <= _parse_wp_time(wp["time"]) <= end_time]
        for key, waypoints in streams.items()
    }


def resolve_location(
    latitude: float,
    longitude: float,
) -> dict[str, str] | None:
    """Get city, town, and country via geocoding.

    Delegates to ``activities.activity.utils.location_based_on_coordinates``.

    Args:
        latitude: WGS-84 latitude in decimal degrees.
        longitude: WGS-84 longitude in decimal degrees.

    Returns:
        Dict with keys ``'city'``, ``'town'``, ``'country'``, or
        ``None`` on geocoding error.
    """
    # Imported lazily to avoid a circular import (see _compute_lap_metrics).
    import activities.activity.utils as activities_utils

    return activities_utils.location_based_on_coordinates(latitude, longitude)


def resolve_timezone_from_lat_lon(
    latitude: float,
    longitude: float,
    fallback_tz: str,
) -> str:
    """Get timezone string via TimezoneFinder with a fallback.

    Args:
        latitude: WGS-84 latitude in decimal degrees.
        longitude: WGS-84 longitude in decimal degrees.
        fallback_tz: Timezone string to return when TimezoneFinder
            returns ``None``.

    Returns:
        IANA timezone string (e.g. ``'Europe/Lisbon'``).
    """
    tf = TimezoneFinder()
    tz = tf.timezone_at(lat=latitude, lng=longitude)
    return tz if tz is not None else fallback_tz


def calculate_power_metrics(
    power_waypoints: list[dict],
) -> tuple[float | None, float | None, float | None]:
    """Calculate average, max, and normalised power from a power stream.

    Args:
        power_waypoints: List of waypoint dicts each containing a
            ``'power'`` key with a numeric value.  Must be non-empty.

    Returns:
        Tuple of ``(avg_power, max_power, normalized_power)``.  Any
        value may be ``None`` if the stream contains no valid readings.
    """
    # Imported lazily to avoid a circular import (see _compute_lap_metrics).
    import activities.activity.utils as activities_utils

    avg_power, max_power = activities_utils.calculate_avg_and_max(power_waypoints, "power")
    normalized_power = activities_utils.calculate_np(power_waypoints)
    return avg_power, max_power, normalized_power


def compute_distance_from_waypoints(lat_lon_waypoints: list[dict]) -> float:
    """Compute total distance in metres from a GPS track.

    Sums the geodesic distance between consecutive waypoints. Used as a
    fallback when a source file does not provide a summary distance (e.g. a
    FIT session frame without ``total_distance``). Mirrors the accumulation
    the GPX importer already performs point-by-point.

    Args:
        lat_lon_waypoints: Ordered list of dicts each containing ``'lat'``
            and ``'lon'`` numeric keys.

    Returns:
        Total distance in metres. ``0.0`` if fewer than two valid points.
    """
    total = 0.0
    for i in range(1, len(lat_lon_waypoints)):
        prev_point = lat_lon_waypoints[i - 1]
        current_point = lat_lon_waypoints[i]
        if (
            prev_point.get("lat") is None
            or prev_point.get("lon") is None
            or current_point.get("lat") is None
            or current_point.get("lon") is None
        ):
            continue
        total += geodesic(
            (prev_point["lat"], prev_point["lon"]),
            (current_point["lat"], current_point["lon"]),
        ).meters
    return total
