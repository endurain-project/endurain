"""Utilities for parsing TCX files into activity data."""

from typing import Any

import tcxreader
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.activity.schema as activities_schema
import activities.activity.utils as activities_utils
import activities.activity_file_import.utils as activity_file_import_utils
import core.config as core_config
import core.logger as core_logger
import core.timezone as core_timezone
import users.users_default_gear.utils as user_default_gear_utils
import users.users_privacy_settings.models as users_privacy_settings_models


def _parse_lap_power(
    lap: Any,
) -> tuple[float | None, float | None, float | None]:
    """
    Extract power metrics from a single TCX lap.

    Args:
        lap: A TCX lap object from tcxreader.

    Returns:
        Tuple of (avg_power, max_power, normalized_power),
        each None when no power data is available.
    """
    power_waypoints: list[dict] = []
    for trackpoint in lap.trackpoints:
        if hasattr(trackpoint, "tpx_ext") and "Watts" in trackpoint.tpx_ext and trackpoint.time is not None:
            power_waypoints.append(
                {
                    "time": core_timezone.format_utc(trackpoint.time),
                    "power": trackpoint.tpx_ext["Watts"],
                }
            )

    if not power_waypoints:
        return None, None, None

    return activity_file_import_utils.calculate_power_metrics(power_waypoints)


def _parse_laps(
    tcx_file: Any,
) -> list[dict]:
    """
    Parse all TCX laps into structured dicts.

    Args:
        tcx_file: Parsed TCX file object.

    Returns:
        List of lap dicts with metrics.
    """
    laps: list[dict] = []

    for lap in tcx_file.laps:
        if lap.start_time is None:
            continue

        lap_avg_pw, lap_max_pw, lap_np = _parse_lap_power(lap)

        max_spd_val = lap.tpx_ext_stats.get("Speed", {}).get("max", 0)

        laps.append(
            {
                "start_time": core_timezone.to_utc_aware(lap.start_time),
                "start_position_lat": (lap.trackpoints[0].latitude),
                "start_position_long": (lap.trackpoints[0].longitude),
                "end_position_lat": (lap.trackpoints[-1].latitude),
                "end_position_long": (lap.trackpoints[-1].longitude),
                "total_elapsed_time": (
                    (lap.end_time - lap.start_time).total_seconds() if lap.start_time and lap.end_time else None
                ),
                "total_timer_time": (
                    (lap.end_time - lap.start_time).total_seconds() if lap.start_time and lap.end_time else None
                ),
                "total_distance": (round(lap.distance) if lap.distance else None),
                "total_calories": (round(lap.calories) if lap.calories else None),
                "avg_heart_rate": (round(lap.hr_avg) if lap.hr_avg else None),
                "max_heart_rate": (round(lap.hr_max) if lap.hr_max else None),
                "avg_cadence": (round(lap.cadence_avg) if lap.cadence_avg else None),
                "max_cadence": (round(lap.cadence_max) if lap.cadence_max else None),
                "avg_power": (round(lap_avg_pw) if lap_avg_pw else None),
                "max_power": (round(lap_max_pw) if lap_max_pw else None),
                "total_ascent": (round(lap.ascent) if lap.ascent else None),
                "total_descent": (round(lap.descent) if lap.descent else None),
                "normalized_power": (round(lap_np) if lap_np else None),
                "enhanced_avg_pace": (1 / lap.avg_speed if lap.avg_speed and lap.avg_speed != 0 else None),
                "enhanced_avg_speed": (lap.avg_speed if lap.avg_speed else None),
                "enhanced_max_pace": (1 / max_spd_val if max_spd_val and max_spd_val != 0 else None),
                "enhanced_max_speed": (max_spd_val if max_spd_val else None),
            }
        )

    return laps


def _extract_waypoints(
    trackpoints: list[dict],
    tcx_file: Any,
) -> dict:
    """
    Extract typed waypoint lists from trackpoints.

    Args:
        trackpoints: Trackpoints as dicts from
            tcx_file.trackpoints_to_dict().
        tcx_file: Parsed TCX file object.

    Returns:
        Dict with lat_lon, hr, cad, ele, power,
        vel, and pace waypoint lists.
    """
    lat_lon_waypoints = [
        {
            "time": core_timezone.format_utc(tp["time"]),
            "lat": tp["latitude"],
            "lon": tp["longitude"],
        }
        for tp in trackpoints
        if tp.get("time") is not None
    ]

    hr_waypoints = [
        {
            "time": core_timezone.format_utc(tp["time"]),
            "hr": tp["hr_value"],
        }
        for tp in trackpoints
        if "hr_value" in tp and tp.get("time") is not None
    ]

    cad_waypoints = [
        {
            "time": core_timezone.format_utc(tp["time"]),
            "cad": tp["cadence"],
        }
        for tp in trackpoints
        if tp.get("cadence") is not None and tp.get("time") is not None
    ]
    if not cad_waypoints:
        cad_waypoints = [
            {
                "time": core_timezone.format_utc(tp.time),
                "cad": tp.tpx_ext["RunCadence"],
            }
            for tp in tcx_file.trackpoints
            if (hasattr(tp, "tpx_ext") and "RunCadence" in tp.tpx_ext and tp.time is not None)
        ]

    ele_waypoints = [
        {
            "time": core_timezone.format_utc(tp["time"]),
            "ele": tp["elevation"],
        }
        for tp in trackpoints
        if "elevation" in tp and tp.get("time") is not None
    ]

    power_waypoints = [
        {
            "time": core_timezone.format_utc(tp.time),
            "power": tp.tpx_ext["Watts"],
        }
        for tp in tcx_file.trackpoints
        if (hasattr(tp, "tpx_ext") and "Watts" in tp.tpx_ext and tp.time is not None)
    ]

    vel_waypoints: list[dict] = []
    pace_waypoints: list[dict] = []
    last_time = None
    prev_lat = None
    prev_lon = None

    for tp in trackpoints:
        lat = tp["latitude"]
        lon = tp["longitude"]
        time_val = tp["time"]

        if time_val is None:
            continue

        timestamp = core_timezone.format_utc(time_val)

        instant_speed = activities_utils.calculate_instant_speed(
            last_time,
            time_val,
            lat,
            lon,
            prev_lat,
            prev_lon,
        )

        instant_pace = 1 / instant_speed if instant_speed > 0 else 0

        activities_utils.append_if_not_none(
            vel_waypoints,
            timestamp,
            instant_speed,
            "vel",
        )
        activities_utils.append_if_not_none(
            pace_waypoints,
            timestamp,
            instant_pace,
            "pace",
        )

        prev_lat, prev_lon, last_time = (
            lat,
            lon,
            time_val,
        )

    return {
        "lat_lon_waypoints": lat_lon_waypoints,
        "hr_waypoints": hr_waypoints,
        "cad_waypoints": cad_waypoints,
        "ele_waypoints": ele_waypoints,
        "power_waypoints": power_waypoints,
        "vel_waypoints": vel_waypoints,
        "pace_waypoints": pace_waypoints,
    }


def _build_activity(
    tcx_file: Any,
    user_id: int,
    activity_name: str,
    activity_type: int,
    distance: int,
    timezone: str,
    pace: float | None,
    city: str | None,
    town: str | None,
    country: str | None,
    avg_power: float | None,
    max_power: float | None,
    norm_power: float | None,
    gear_id: int | None,
    user_privacy_settings: users_privacy_settings_models.UsersPrivacySettings,
) -> activities_schema.Activity:
    """
    Construct an Activity schema from parsed TCX data.

    Args:
        tcx_file: Parsed TCX file object.
        user_id: ID of the owning user.
        activity_name: Name for the activity.
        activity_type: Numeric activity type.
        distance: Total distance in metres.
        timezone: IANA timezone string.
        pace: Overall pace value or None.
        city: City name or None.
        town: Town name or None.
        country: Country name or None.
        avg_power: Average power or None.
        max_power: Maximum power or None.
        norm_power: Normalized power or None.
        gear_id: Gear ID or None.
        user_privacy_settings: User privacy settings
            ORM instance.

    Returns:
        Populated Activity Pydantic schema.
    """
    elapsed = (
        (tcx_file.end_time - tcx_file.start_time).total_seconds() if tcx_file.start_time and tcx_file.end_time else None
    )

    privacy_kwargs = activity_file_import_utils.build_activity_privacy_kwargs(user_privacy_settings)

    return activities_schema.Activity(
        user_id=user_id,
        name=activity_name,
        distance=distance,
        activity_type=activity_type,
        timezone=timezone,
        start_time=(core_timezone.format_utc(tcx_file.start_time) if tcx_file.start_time else None),
        end_time=(core_timezone.format_utc(tcx_file.end_time) if tcx_file.end_time else None),
        total_elapsed_time=elapsed,
        total_timer_time=elapsed,
        city=city,
        town=town,
        country=country,
        elevation_gain=(round(tcx_file.ascent) if tcx_file.ascent else None),
        elevation_loss=(round(tcx_file.descent) if tcx_file.descent else None),
        pace=pace,
        average_power=(round(avg_power) if avg_power else None),
        max_power=(round(max_power) if max_power else None),
        normalized_power=(round(norm_power) if norm_power else None),
        average_hr=(round(tcx_file.hr_avg) if tcx_file.hr_avg else None),
        max_hr=(round(tcx_file.hr_max) if tcx_file.hr_max else None),
        average_cad=(round(tcx_file.cadence_avg) if tcx_file.cadence_avg else None),
        max_cad=(round(tcx_file.cadence_max) if tcx_file.cadence_max else None),
        calories=(tcx_file.calories if tcx_file.calories else None),
        gear_id=gear_id,
        **privacy_kwargs,
    )


def parse_tcx_file(
    file: str,
    user_id: int,
    user_privacy_settings: users_privacy_settings_models.UsersPrivacySettings,
    db: Session,
    activity_name_input: str | None = None,
) -> dict:
    """
    Parse a TCX file and return activity data.

    Args:
        file: Path to the TCX file.
        user_id: ID of the owning user.
        user_privacy_settings: User privacy settings
            ORM instance.
        db: Database session.
        activity_name_input: Optional custom activity
            name.

    Returns:
        Dict with activity, waypoints, laps and
        associated metadata.

    Raises:
        HTTPException: When the TCX file cannot be
            parsed or processed.
    """
    try:
        tcx_file = tcxreader.TCXReader().read(file)
        trackpoints = tcx_file.trackpoints_to_dict()

        timezone = core_config.settings.TZ
        pace: float | None = None
        city: str | None = None
        town: str | None = None
        country: str | None = None
        activity_name = activity_name_input if activity_name_input else "Workout"
        avg_power: float | None = None
        max_power: float | None = None
        norm_power: float | None = None

        activity_type = activities_utils.define_activity_type(tcx_file.activity_type)

        gear_id = user_default_gear_utils.get_user_default_gear_by_activity_type(user_id, activity_type, db)

        laps = _parse_laps(tcx_file)
        waypoints = _extract_waypoints(trackpoints, tcx_file)

        lat_lon_wp = waypoints["lat_lon_waypoints"]
        power_wp = waypoints["power_waypoints"]

        distance = round(tcx_file.distance) if tcx_file.distance else 0
        if not distance and lat_lon_wp:
            # Some TCX sources omit the summary Distance element even when a
            # GPS track is present. Fall back to the geodesic sum over the
            # track, mirroring the FIT/GPX importers.
            distance = round(activity_file_import_utils.compute_distance_from_waypoints(lat_lon_wp))

        if lat_lon_wp:
            pace = activities_utils.calculate_pace(
                distance,
                trackpoints[0]["time"],
                trackpoints[-1]["time"],
            )

            location_data = activity_file_import_utils.resolve_location(
                trackpoints[0]["latitude"],
                trackpoints[0]["longitude"],
            )

            if location_data:
                city = location_data["city"]
                town = location_data["town"]
                country = location_data["country"]

            timezone = activity_file_import_utils.resolve_timezone_from_lat_lon(
                trackpoints[0]["latitude"],
                trackpoints[0]["longitude"],
                timezone,
            )

        if power_wp:
            avg_power, max_power, norm_power = activity_file_import_utils.calculate_power_metrics(power_wp)

        # Recompute avg/max HR from waypoints, excluding zeros (zero is not a
        # valid HR value — it means the sensor was disconnected). This overrides
        # the device-computed value from the TCX file which may include zeros.
        hr_wp = waypoints.get("hr_waypoints", [])
        if hr_wp:
            recomputed_avg, recomputed_max = activities_utils.calculate_avg_and_max(
                hr_wp,
                "hr",
            )
            if recomputed_avg:
                tcx_file.hr_avg = recomputed_avg
            if recomputed_max:
                tcx_file.hr_max = recomputed_max

        activity = _build_activity(
            tcx_file=tcx_file,
            user_id=user_id,
            activity_name=activity_name,
            activity_type=activity_type,
            distance=distance,
            timezone=timezone,
            pace=pace,
            city=city,
            town=town,
            country=country,
            avg_power=avg_power,
            max_power=max_power,
            norm_power=norm_power,
            gear_id=gear_id,
            user_privacy_settings=user_privacy_settings,
        )

        waypoints_combined = {
            **waypoints,
            "power_waypoints": power_wp,
            "lat_lon_waypoints": lat_lon_wp,
        }
        return activity_file_import_utils.build_activity_file_payload(activity, waypoints_combined, laps)

    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        core_logger.print_to_log(
            f"Error in parse_tcx_file - {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=(status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=(f"Can't open TCX file: {err}"),
        ) from err
