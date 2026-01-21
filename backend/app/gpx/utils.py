import gpxpy
from geopy.distance import geodesic
from timezonefinder import TimezoneFinder
from sqlalchemy.orm import Session
from datetime import datetime

from fastapi import HTTPException, status

import activities.activity.utils as activities_utils
import activities.activity.schema as activities_schema

import users.users_default_gear.utils as user_default_gear_utils

import users.users_privacy_settings.models as users_privacy_settings_models
import users.users_privacy_settings.utils as users_privacy_settings_utils

import core.logger as core_logger
import core.config as core_config


def parse_gpx_file(
    file: str,
    user_id: int,
    user_privacy_settings: users_privacy_settings_models.UsersPrivacySettings,
    db: Session,
    activity_name_input: str | None = None,
) -> dict:
    try:
        # Create an instance of TimezoneFinder
        tf = TimezoneFinder()
        timezone = core_config.TZ

        # Initialize default values for various variables
        activity_type = "Workout"
        calories = None
        distance = 0
        avg_hr = None
        max_hr = None
        avg_cadence = None
        max_cadence = None
        first_waypoint_time = None
        last_waypoint_time = None
        avg_power = None
        max_power = None
        ele_gain = None
        ele_loss = None
        np = None
        avg_speed = None
        max_speed = None
        activity_name = activity_name_input if activity_name_input else "Workout"
        activity_description = None
        process_one_time_fields = 0
        gear_id = None

        city = None
        town = None
        country = None
        pace = 0

        # Arrays to store waypoint data
        lat_lon_waypoints = []
        ele_waypoints = []
        hr_waypoints = []
        cad_waypoints = []
        power_waypoints = []
        vel_waypoints = []
        pace_waypoints = []

        # Initialize variables to store previous latitude and longitude
        prev_latitude, prev_longitude = None, None

        # Initialize variables to store whether elevation, power, heart rate, cadence, and velocity are set
        is_lat_lon_set = False
        is_elevation_set = False
        is_power_set = False
        is_heart_rate_set = False
        is_cadence_set = False
        is_velocity_set = False

        # Parse the GPX file
        with open(file, "r") as gpx_file:
            gpx = gpxpy.parse(gpx_file)

            if gpx.tracks:
                # Iterate over tracks in the GPX file
                for track in gpx.tracks:
                    # Set activity name, description, and type if available
                    activity_name = (
                        track.name
                        if track.name
                        else gpx.name if gpx.name else "Workout"
                    )
                    activity_description = (
                        track.description
                        if track.description
                        else gpx.description if gpx.description else None
                    )
                    activity_type = track.type if track.type else "Workout"

                    if track.segments:
                        # Iterate over segments in each track
                        for segment in track.segments:
                            # Iterate over points in each segment
                            for point in segment.points:
                                # Extract latitude and longitude from the point
                                latitude, longitude = point.latitude, point.longitude

                                # Extract elevation, time, and location details
                                elevation, time = point.elevation, point.time

                                # Skip trackpoints without time data (common in some OsmAnd exports)
                                if time is None:
                                    continue

                                # Calculate distance between waypoints
                                if (
                                    prev_latitude is not None
                                    and prev_longitude is not None
                                ):
                                    distance += geodesic(
                                        (prev_latitude, prev_longitude),
                                        (latitude, longitude),
                                    ).meters

                                if elevation != 0:
                                    is_elevation_set = True

                                if first_waypoint_time is None:
                                    first_waypoint_time = point.time

                                if process_one_time_fields == 0:
                                    # Use geocoding API to get city, town, and country based on coordinates
                                    location_data = (
                                        activities_utils.location_based_on_coordinates(
                                            latitude, longitude
                                        )
                                    )

                                    # Extract city, town, and country from location data
                                    if location_data:
                                        city = location_data["city"]
                                        town = location_data["town"]
                                        country = location_data["country"]

                                        process_one_time_fields = 1

                                # Extract heart rate, cadence, and power data from point extensions
                                heart_rate, cadence, power = 0, 0, 0

                                if point.extensions:
                                    # Iterate through each extension element
                                    for extension in point.extensions:
                                        if extension.tag.endswith(
                                            "TrackPointExtension"
                                        ):
                                            hr_element = extension.find(
                                                ".//{http://www.garmin.com/xmlschemas/TrackPointExtension/v1}hr"
                                            )
                                            if hr_element is not None:
                                                heart_rate = hr_element.text
                                            cad_element = extension.find(
                                                ".//{http://www.garmin.com/xmlschemas/TrackPointExtension/v1}cad"
                                            )
                                            if cad_element is not None:
                                                cadence = cad_element.text

                                            # OpenTracks extension
                                            if (
                                                hr_element is None
                                                and cad_element is None
                                            ):
                                                for child in extension:
                                                    if child.tag.endswith("hr"):
                                                        heart_rate = child.text
                                                    elif child.tag.endswith("cad"):
                                                        cadence = child.text
                                        elif extension.tag.endswith("power"):
                                            # Extract 'power' value
                                            power = (
                                                int(extension.text)
                                                if extension.text
                                                else 0
                                            )
                                        elif extension.tag.endswith("heartrate"):
                                            # Tissot smartwatch and similar devices extension
                                            heart_rate = (
                                                int(extension.text)
                                                if extension.text
                                                else 0
                                            )

                                # Check if heart rate, cadence, power are set
                                if heart_rate != 0:
                                    is_heart_rate_set = True

                                if cadence != 0:
                                    is_cadence_set = True

                                if power != 0:
                                    is_power_set = True
                                else:
                                    power = None

                                # Calculate instant speed, pace, and update waypoint arrays
                                instant_speed = (
                                    activities_utils.calculate_instant_speed(
                                        last_waypoint_time,
                                        time,
                                        latitude,
                                        longitude,
                                        prev_latitude,
                                        prev_longitude,
                                    )
                                )

                                # Calculate instance pace
                                instant_pace = 0
                                if instant_speed > 0:
                                    instant_pace = 1 / instant_speed
                                    is_velocity_set = True

                                timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

                                # Append waypoint data to respective arrays
                                if latitude is not None and longitude is not None:
                                    lat_lon_waypoints.append(
                                        {
                                            "time": timestamp,
                                            "lat": latitude,
                                            "lon": longitude,
                                        }
                                    )
                                    is_lat_lon_set = True

                                activities_utils.append_if_not_none(
                                    ele_waypoints, timestamp, elevation, "ele"
                                )
                                activities_utils.append_if_not_none(
                                    hr_waypoints, timestamp, heart_rate, "hr"
                                )
                                activities_utils.append_if_not_none(
                                    cad_waypoints, timestamp, cadence, "cad"
                                )
                                activities_utils.append_if_not_none(
                                    power_waypoints, timestamp, power, "power"
                                )
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
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid GPX file - no segments found in the GPX file",
                        )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid GPX file - no tracks found in the GPX file",
                )

        # Check if we have at least one valid trackpoint with time data
        if first_waypoint_time is None or last_waypoint_time is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid GPX file - no trackpoints with valid time data found",
            )

        # Calculate elevation gain/loss, pace, average speed, and average power
        if ele_waypoints:
            ele_gain, ele_loss = activities_utils.compute_elevation_gain_and_loss(
                elevations=ele_waypoints
            )

        pace = activities_utils.calculate_pace(
            distance, first_waypoint_time, last_waypoint_time
        )

        # Activity type
        activity_type = activities_utils.define_activity_type(activity_type)

        gear_id = user_default_gear_utils.get_user_default_gear_by_activity_type(
            user_id, activity_type, db
        )

        # Calculate average and maximum heart rate
        if hr_waypoints:
            avg_hr, max_hr = activities_utils.calculate_avg_and_max(hr_waypoints, "hr")

        # Calculate average and maximum cadence
        if cad_waypoints:
            avg_cadence, max_cadence = activities_utils.calculate_avg_and_max(
                cad_waypoints, "cad"
            )

        # Calculate average and maximum velocity
        if vel_waypoints:
            avg_speed, max_speed = activities_utils.calculate_avg_and_max(
                vel_waypoints, "vel"
            )

        # Calculate average and maximum power
        if power_waypoints:
            avg_power, max_power = activities_utils.calculate_avg_and_max(
                power_waypoints, "power"
            )

            # Calculate normalised power
            np = activities_utils.calculate_np(power_waypoints)

        # Calculate the elapsed time
        elapsed_time = last_waypoint_time - first_waypoint_time

        if activity_type != 3 and activity_type != 7:
            if is_lat_lon_set:
                timezone = tf.timezone_at(
                    lat=lat_lon_waypoints[0]["lat"],
                    lng=lat_lon_waypoints[0]["lon"],
                )

        # Create an Activity object with parsed data
        activity = activities_schema.Activity(
            user_id=user_id,
            name=activity_name,
            description=activity_description,
            distance=round(distance) if distance else 0,
            activity_type=activity_type,
            start_time=first_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S"),
            end_time=last_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S"),
            timezone=timezone,
            total_elapsed_time=elapsed_time.total_seconds(),
            total_timer_time=elapsed_time.total_seconds(),
            city=city,
            town=town,
            country=country,
            elevation_gain=round(ele_gain) if ele_gain else None,
            elevation_loss=round(ele_loss) if ele_loss else None,
            pace=pace,
            average_speed=avg_speed,
            max_speed=max_speed,
            average_power=round(avg_power) if avg_power else None,
            max_power=round(max_power) if max_power else None,
            normalized_power=round(np) if np else None,
            average_hr=round(avg_hr) if avg_hr else None,
            max_hr=round(max_hr) if max_hr else None,
            average_cad=round(avg_cadence) if avg_cadence else None,
            max_cad=round(max_cadence) if max_cadence else None,
            calories=calories,
            visibility=users_privacy_settings_utils.visibility_to_int(
                user_privacy_settings.default_activity_visibility
            ),
            gear_id=gear_id,
            strava_gear_id=None,
            strava_activity_id=None,
            garminconnect_activity_id=None,
            garminconnect_gear_id=None,
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

        # Generate activity laps
        laps = generate_activity_laps(
            lat_lon_waypoints,
            ele_waypoints,
            power_waypoints,
            hr_waypoints,
            cad_waypoints,
            vel_waypoints,
        )

        # Return parsed data as a dictionary
        return {
            "activity": activity,
            "is_elevation_set": is_elevation_set,
            "ele_waypoints": ele_waypoints,
            "is_power_set": is_power_set,
            "power_waypoints": power_waypoints,
            "is_heart_rate_set": is_heart_rate_set,
            "hr_waypoints": hr_waypoints,
            "is_velocity_set": is_velocity_set,
            "vel_waypoints": vel_waypoints,
            "pace_waypoints": pace_waypoints,
            "is_cadence_set": is_cadence_set,
            "cad_waypoints": cad_waypoints,
            "is_lat_lon_set": is_lat_lon_set,
            "lat_lon_waypoints": lat_lon_waypoints,
            "laps": laps,
        }

    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in parse_gpx_file - {str(err)}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Can't open GPX file: {str(err)}",
        ) from err


def generate_activity_laps(
    lat_lon_waypoints: list[dict],
    ele_waypoints: list[dict],
    power_waypoints: list[dict],
    hr_waypoints: list[dict],
    cad_waypoints: list[dict],
    vel_waypoints: list[dict],
    distance_per_lap_km: float = 1.0,
) -> list[dict]:
    laps = []
    current_lap_distance = 0.0
    lap_start = None
    lap_ele_waypoints = []
    lap_power_waypoints = []
    lap_hr_waypoints = []
    lap_cad_waypoints = []
    lap_vel_waypoints = []

    def filter_waypoints(waypoints, start_time, end_time):
        return [
            waypoint
            for waypoint in waypoints
            if datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S")
            <= datetime.strptime(waypoint["time"], "%Y-%m-%dT%H:%M:%S")
            <= datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S")
        ]

    for i in range(1, len(lat_lon_waypoints)):
        # Get the current and previous waypoints
        prev_point = lat_lon_waypoints[i - 1]
        current_point = lat_lon_waypoints[i]

        # Calculate the distance between the two waypoints
        segment_distance = geodesic(
            (prev_point["lat"], prev_point["lon"]),
            (current_point["lat"], current_point["lon"]),
        ).kilometers

        # Accumulate the distance
        current_lap_distance += segment_distance

        # Set the start of the lap if not already set
        if lap_start is None:
            lap_start = prev_point

        # Check if the current lap distance exceeds or equals the lap distance
        if current_lap_distance >= distance_per_lap_km:
            # Filter waypoints for the current lap
            start_time = lap_start["time"]
            end_time = current_point["time"]
            lap_ele_waypoints = filter_waypoints(ele_waypoints, start_time, end_time)
            lap_power_waypoints = filter_waypoints(
                power_waypoints, start_time, end_time
            )
            lap_hr_waypoints = filter_waypoints(hr_waypoints, start_time, end_time)
            lap_cad_waypoints = filter_waypoints(cad_waypoints, start_time, end_time)
            lap_vel_waypoints = filter_waypoints(vel_waypoints, start_time, end_time)
            ele_gain = None
            ele_loss = None
            avg_hr = None
            max_hr = None
            avg_cadence = None
            max_cadence = None
            avg_speed = None
            max_speed = None
            avg_power = None
            max_power = None
            np = None

            # Calculate total ascent and descent
            if lap_ele_waypoints:
                ele_gain, ele_loss = activities_utils.compute_elevation_gain_and_loss(
                    elevations=lap_ele_waypoints
                )

            # Calculate average and maximum heart rate
            if lap_hr_waypoints:
                avg_hr, max_hr = activities_utils.calculate_avg_and_max(
                    lap_hr_waypoints, "hr"
                )

            # Calculate average and maximum cadence
            if lap_cad_waypoints:
                avg_cadence, max_cadence = activities_utils.calculate_avg_and_max(
                    lap_cad_waypoints, "cad"
                )

            # Calculate average and maximum velocity
            if lap_vel_waypoints:
                avg_speed, max_speed = activities_utils.calculate_avg_and_max(
                    lap_vel_waypoints, "vel"
                )

            # Calculate average and maximum power
            if lap_power_waypoints:
                avg_power, max_power = activities_utils.calculate_avg_and_max(
                    lap_power_waypoints, "power"
                )

                # Calculate normalised power
                np = activities_utils.calculate_np(lap_power_waypoints)

            # Create a lap
            laps.append(
                {
                    "start_time": lap_start["time"],
                    "start_position_lat": lap_start["lat"],
                    "start_position_long": lap_start["lon"],
                    "end_position_lat": current_point["lat"],
                    "end_position_long": current_point["lon"],
                    "total_elapsed_time": (
                        datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S")
                        - datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S")
                    ).total_seconds(),
                    "total_timer_time": (
                        datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S")
                        - datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S")
                    ).total_seconds(),
                    "total_distance": current_lap_distance * 1000,
                    "avg_heart_rate": round(avg_hr) if avg_hr else None,
                    "max_heart_rate": round(max_hr) if max_hr else None,
                    "avg_cadence": round(avg_cadence) if avg_cadence else None,
                    "max_cadence": round(max_cadence) if max_cadence else None,
                    "avg_power": round(avg_power) if avg_power else None,
                    "max_power": round(max_power) if max_power else None,
                    "total_ascent": round(ele_gain) if ele_gain else None,
                    "total_descent": round(ele_loss) if ele_loss else None,
                    "normalized_power": round(np) if np else None,
                    "enhanced_avg_pace": (
                        1 / avg_speed
                        if avg_speed != 0 and avg_speed is not None
                        else None
                    ),
                    "enhanced_avg_speed": avg_speed,
                    "enhanced_max_pace": (
                        1 / max_speed
                        if max_speed != 0 and max_speed is not None
                        else None
                    ),
                    "enhanced_max_speed": max_speed,
                }
            )

            # Reset for the next lap
            lap_start = current_point
            current_lap_distance = 0.0

    # Add the final lap if it exists and is less than the lap distance
    if lap_start is not None and current_lap_distance > 0:
        start_time = lap_start["time"]
        end_time = lat_lon_waypoints[-1]["time"]
        lap_ele_waypoints = filter_waypoints(ele_waypoints, start_time, end_time)
        lap_power_waypoints = filter_waypoints(power_waypoints, start_time, end_time)
        lap_hr_waypoints = filter_waypoints(hr_waypoints, start_time, end_time)
        lap_cad_waypoints = filter_waypoints(cad_waypoints, start_time, end_time)
        lap_vel_waypoints = filter_waypoints(vel_waypoints, start_time, end_time)
        ele_gain, ele_loss = None, None
        avg_hr, max_hr = None, None
        avg_cadence, max_cadence = None, None
        avg_speed, max_speed = None, None
        avg_power, max_power, np = None, None, None

        # Calculate total ascent and descent
        if lap_ele_waypoints:
            ele_gain, ele_loss = activities_utils.compute_elevation_gain_and_loss(
                lap_ele_waypoints
            )

        # Calculate average and maximum heart rate
        if lap_hr_waypoints:
            avg_hr, max_hr = activities_utils.calculate_avg_and_max(
                lap_hr_waypoints, "hr"
            )

        # Calculate average and maximum cadence
        if lap_cad_waypoints:
            avg_cadence, max_cadence = activities_utils.calculate_avg_and_max(
                lap_cad_waypoints, "cad"
            )

        # Calculate average and maximum velocity
        if lap_vel_waypoints:
            avg_speed, max_speed = activities_utils.calculate_avg_and_max(
                lap_vel_waypoints, "vel"
            )

        # Calculate average and maximum power
        if lap_power_waypoints:
            avg_power, max_power = activities_utils.calculate_avg_and_max(
                lap_power_waypoints, "power"
            )

            # Calculate normalised power
            np = activities_utils.calculate_np(lap_power_waypoints)

        laps.append(
            {
                "start_time": lap_start["time"],
                "start_position_lat": lap_start["lat"],
                "start_position_long": lap_start["lon"],
                "end_position_lat": lat_lon_waypoints[-1]["lat"],
                "end_position_long": lat_lon_waypoints[-1]["lon"],
                "total_elapsed_time": (
                    datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S")
                    - datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S")
                ).total_seconds(),
                "total_timer_time": (
                    datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S")
                    - datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S")
                ).total_seconds(),
                "total_distance": current_lap_distance * 1000,
                "avg_heart_rate": round(avg_hr) if avg_hr else None,
                "max_heart_rate": round(max_hr) if max_hr else None,
                "avg_cadence": round(avg_cadence) if avg_cadence else None,
                "max_cadence": round(max_cadence) if max_cadence else None,
                "avg_power": round(avg_power) if avg_power else None,
                "max_power": round(max_power) if max_power else None,
                "total_ascent": round(ele_gain) if ele_gain else None,
                "total_descent": round(ele_loss) if ele_loss else None,
                "normalized_power": round(np) if np else None,
                "enhanced_avg_pace": (
                    1 / avg_speed if avg_speed != 0 and avg_speed is not None else None
                ),
                "enhanced_avg_speed": avg_speed,
                "enhanced_max_pace": (
                    1 / max_speed if max_speed != 0 and max_speed is not None else None
                ),
                "enhanced_max_speed": max_speed,
            }
        )

    return laps
