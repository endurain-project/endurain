from collections import defaultdict
from timezonefinder import TimezoneFinder
from datetime import datetime

import tcxreader
import activities.activity.schema as activities_schema
import activities.activity.utils as activities_utils

import users.users_default_gear.utils as user_default_gear_utils

import users.users_privacy_settings.utils as users_privacy_settings_utils

import core.config as core_config


def parse_tcx_file(
    file, user_id, user_privacy_settings, db, activity_name_input: str | None = None
) -> dict:
    tcx_file = tcxreader.TCXReader().read(file)
    trackpoints = tcx_file.trackpoints_to_dict()

    # Create an instance of TimezoneFinder
    tf = TimezoneFinder()
    timezone = core_config.TZ

    # Initialize variables
    gear_id = None
    pace = None
    city = None
    town = None
    country = None
    activity_name = activity_name_input if activity_name_input else "Workout"
    avg_power = None
    max_power = None
    np = None
    last_waypoint_time, prev_latitude, prev_longitude = None, None, None
    cad_waypoints = []
    vel_waypoints = []
    pace_waypoints = []

    laps = []

    activity_type = activities_utils.define_activity_type(tcx_file.activity_type)

    if gear_id is None:
        gear_id = user_default_gear_utils.get_user_default_gear_by_activity_type(
            user_id, activity_type, db
        )

    for lap in tcx_file.laps:
        if lap.start_time is None:
            continue

        lap_power_waypoints = []
        lap_avg_power = None
        lap_max_power = None
        lap_np = None

        for trackpoint in lap.trackpoints:
            if hasattr(trackpoint, "tpx_ext") and "Watts" in trackpoint.tpx_ext:
                lap_power_waypoints.append(
                    {
                        "time": trackpoint.time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "power": trackpoint.tpx_ext["Watts"],
                    }
                )

        if lap_power_waypoints:
            lap_avg_power, lap_max_power = activities_utils.calculate_avg_and_max(
                lap_power_waypoints, "power"
            )

            # Calculate normalised power
            lap_np = activities_utils.calculate_np(lap_power_waypoints)

        laps.append(
            {
                "start_time": lap.start_time,
                "start_position_lat": lap.trackpoints[0].latitude,
                "start_position_long": lap.trackpoints[0].longitude,
                "end_position_lat": lap.trackpoints[-1].latitude,
                "end_position_long": lap.trackpoints[-1].longitude,
                "total_elapsed_time": (
                    (lap.end_time - lap.start_time).total_seconds()
                    if lap.start_time and lap.end_time
                    else None
                ),
                "total_timer_time": (
                    (lap.end_time - lap.start_time).total_seconds()
                    if lap.start_time and lap.end_time
                    else None
                ),
                "total_distance": round(lap.distance) if lap.distance else None,
                "total_calories": round(lap.calories) if lap.calories else None,
                "avg_heart_rate": round(lap.hr_avg) if lap.hr_avg else None,
                "max_heart_rate": round(lap.hr_max) if lap.hr_max else None,
                "avg_cadence": round(lap.cadence_avg) if lap.cadence_avg else None,
                "max_cadence": round(lap.cadence_max) if lap.cadence_max else None,
                "avg_power": round(lap_avg_power) if lap_avg_power else None,
                "max_power": round(lap_max_power) if lap_max_power else None,
                "total_ascent": round(lap.ascent) if lap.ascent else None,
                "total_descent": round(lap.descent) if lap.descent else None,
                "normalized_power": round(lap_np) if lap_np else None,
                "enhanced_avg_pace": (
                    1 / lap.avg_speed if lap.avg_speed != 0 and lap.avg_speed else None
                ),
                "enhanced_avg_speed": lap.avg_speed if lap.avg_speed else None,
                "enhanced_max_pace": (
                    1 / lap.tpx_ext_stats.get("Speed", {}).get("max", 0)
                    if lap.tpx_ext_stats.get("Speed", {}).get("max", 0) != 0
                    and lap.tpx_ext_stats.get("Speed", {}).get("max", 0)
                    else None
                ),
                "enhanced_max_speed": (
                    lap.tpx_ext_stats.get("Speed", {}).get("max")
                    if lap.tpx_ext_stats.get("Speed", {}).get("max")
                    else None
                ),
            }
        )

    lat_lon_waypoints = [
        {
            "time": trackpoint["time"].strftime("%Y-%m-%dT%H:%M:%S"),
            "lat": trackpoint["latitude"],
            "lon": trackpoint["longitude"],
        }
        for trackpoint in trackpoints
    ]

    hr_waypoints = [
        {
            "time": trackpoint["time"].strftime("%Y-%m-%dT%H:%M:%S"),
            "hr": trackpoint["hr_value"],
        }
        for trackpoint in trackpoints
        if "hr_value" in trackpoint
    ]
    cad_waypoints = [
        {
            "time": trackpoint["time"].strftime("%Y-%m-%dT%H:%M:%S"),
            "cad": trackpoint["cadence"],
        }
        for trackpoint in trackpoints
        if trackpoint.get("cadence") is not None
    ]
    if not cad_waypoints:
        cad_waypoints = [
            {
                "time": trackpoint.time.strftime("%Y-%m-%dT%H:%M:%S"),
                "cad": trackpoint.tpx_ext["RunCadence"],
            }
            for trackpoint in tcx_file.trackpoints
            if hasattr(trackpoint, "tpx_ext") and "RunCadence" in trackpoint.tpx_ext
        ]
    ele_waypoints = [
        {
            "time": trackpoint["time"].strftime("%Y-%m-%dT%H:%M:%S"),
            "ele": trackpoint["elevation"],
        }
        for trackpoint in trackpoints
        if "elevation" in trackpoint
    ]
    power_waypoints = [
        {
            "time": trackpoint.time.strftime("%Y-%m-%dT%H:%M:%S"),
            "power": trackpoint.tpx_ext["Watts"],
        }
        for trackpoint in tcx_file.trackpoints
        if hasattr(trackpoint, "tpx_ext") and "Watts" in trackpoint.tpx_ext
    ]

    for trackpoint in trackpoints:
        latitude, longitude, time = (
            trackpoint["latitude"],
            trackpoint["longitude"],
            trackpoint["time"],
        )

        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

        # Calculate instant speed, pace, and update waypoint arrays
        instant_speed = activities_utils.calculate_instant_speed(
            last_waypoint_time,
            time,
            latitude,
            longitude,
            prev_latitude,
            prev_longitude,
        )

        # Calculate instance pace
        instant_pace = 0
        if instant_speed > 0:
            instant_pace = 1 / instant_speed

        activities_utils.append_if_not_none(
            vel_waypoints, timestamp, instant_speed, "vel"
        )
        activities_utils.append_if_not_none(
            pace_waypoints, timestamp, instant_pace, "pace"
        )

        # Update previous latitude, longitude, and last waypoint time
        prev_latitude, prev_longitude, last_waypoint_time = (
            latitude,
            longitude,
            time,
        )

    distance = round(tcx_file.distance) if tcx_file.distance else 0

    if lat_lon_waypoints:
        # Calculate pace
        pace = activities_utils.calculate_pace(
            distance, trackpoints[0]["time"], trackpoints[-1]["time"]
        )

        # Calculate location data based on the first waypoint
        location_data = activities_utils.location_based_on_coordinates(
            trackpoints[0]["latitude"], trackpoints[0]["longitude"]
        )

        # Extract city, town, and country from location data
        if location_data:
            city = location_data["city"]
            town = location_data["town"]
            country = location_data["country"]

        # Get timezone based on the first waypoint's coordinates
        timezone = tf.timezone_at(
            lat=trackpoints[0]["latitude"],
            lng=trackpoints[0]["longitude"],
        )

    if power_waypoints:
        avg_power, max_power = activities_utils.calculate_avg_and_max(
            power_waypoints, "power"
        )

        # Calculate normalised power
        np = activities_utils.calculate_np(power_waypoints)

    activity = activities_schema.Activity(
        user_id=user_id,
        name=activity_name,
        distance=distance,
        activity_type=activity_type,
        timezone=timezone,
        start_time=tcx_file.start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        end_time=tcx_file.end_time.strftime("%Y-%m-%dT%H:%M:%S"),
        total_elapsed_time=(tcx_file.end_time - tcx_file.start_time).total_seconds(),
        total_timer_time=(tcx_file.end_time - tcx_file.start_time).total_seconds(),
        city=city,
        town=town,
        country=country,
        elevation_gain=round(tcx_file.ascent) if tcx_file.ascent else None,
        elevation_loss=round(tcx_file.descent) if tcx_file.descent else None,
        pace=pace,
        average_power=round(avg_power) if avg_power else None,
        max_power=round(max_power) if max_power else None,
        normalized_power=round(np) if np else None,
        average_hr=round(tcx_file.hr_avg) if tcx_file.hr_avg else None,
        max_hr=round(tcx_file.hr_max) if tcx_file.hr_max else None,
        average_cad=round(tcx_file.cadence_avg) if tcx_file.cadence_avg else None,
        max_cad=round(tcx_file.cadence_max) if tcx_file.cadence_max else None,
        calories=tcx_file.calories if tcx_file.calories else None,
        visibility=users_privacy_settings_utils.visibility_to_int(
            user_privacy_settings.default_activity_visibility
        ),
        gear_id=gear_id,
        hide_start_time=user_privacy_settings.hide_activity_start_time or False,
        hide_location=user_privacy_settings.hide_activity_location or False,
        hide_map=user_privacy_settings.hide_activity_map or False,
        hide_hr=user_privacy_settings.hide_activity_hr or False,
        hide_power=user_privacy_settings.hide_activity_power or False,
        hide_cadence=user_privacy_settings.hide_activity_cadence or False,
        hide_elevation=user_privacy_settings.hide_activity_elevation or False,
        hide_speed=user_privacy_settings.hide_activity_speed or False,
        hide_pace=user_privacy_settings.hide_activity_pace or False,
        hide_laps=user_privacy_settings.hide_activity_laps or False,
        hide_workout_sets_steps=user_privacy_settings.hide_activity_workout_sets_steps
        or False,
        hide_gear=user_privacy_settings.hide_activity_gear or False,
    )

    return {
        "activity": activity,
        "is_elevation_set": bool(ele_waypoints),
        "ele_waypoints": ele_waypoints,
        "is_power_set": bool(power_waypoints),
        "power_waypoints": power_waypoints,
        "is_heart_rate_set": bool(hr_waypoints),
        "hr_waypoints": hr_waypoints,
        "is_velocity_set": bool(vel_waypoints),
        "vel_waypoints": vel_waypoints,
        "pace_waypoints": pace_waypoints,
        "is_cadence_set": bool(cad_waypoints),
        "cad_waypoints": cad_waypoints,
        "is_lat_lon_set": bool(lat_lon_waypoints),
        "lat_lon_waypoints": lat_lon_waypoints,
        "laps": laps,
    }
