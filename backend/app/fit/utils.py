import fitdecode
import logging

from fastapi import HTTPException, status
from datetime import datetime

import activities.utils as activities_utils
import activities.schema as activities_schema
import activity_streams.schema as activity_streams_schema

# Define a logger created on main.py
logger = logging.getLogger("myLogger")


def parse_activity_streams_from_fit_file(parsed_info: dict, activity_id: int):
    # Create a list of tuples containing stream type, is_set, and waypoints
    stream_mapping = {
        1: ("is_heart_rate_set", "hr_waypoints"),
        2: ("is_power_set", "power_waypoints"),
        3: ("is_cadence_set", "cad_waypoints"),
        4: ("is_elevation_set", "ele_waypoints"),
        5: ("is_velocity_set", "vel_waypoints"),
        6: ("is_velocity_set", "pace_waypoints"),
        7: ("lat_lon_waypoints", "lat_lon_waypoints"),
    }

    stream_data_list = [
        (stream_type, parsed_info[is_set_key], parsed_info[waypoints_key])
        for stream_type, (is_set_key, waypoints_key) in stream_mapping.items()
        if parsed_info[is_set_key]
    ]

    # Return activity streams as a list of ActivityStreams objects
    return [
        activity_streams_schema.ActivityStreams(
            activity_id=activity_id,
            stream_type=stream_type,
            stream_waypoints=waypoints,
            strava_activity_stream_id=None,
        )
        for stream_type, is_set, waypoints in stream_data_list
    ]


def parse_fit_file(file: str, user_id: int) -> dict:
    # Open the FIT file
    try:
        # Initialize default values for various variables
        initial_latitude = None
        initial_longitude = None
        activity_type = "Workout"
        calories = None
        distance = None
        avg_hr = None
        max_hr = None
        avg_cadence = None
        max_cadence = None
        first_waypoint_time = None
        last_waypoint_time = None
        total_elapsed_time = None
        total_timer_time = None
        avg_power = None
        max_power = None
        ele_gain = None
        ele_loss = None
        np = None
        avg_speed = None
        max_speed = None
        activity_name = "Workout"
        workout_feeling = None
        workout_rpe = None

        city = None
        town = None
        country = None
        pace = 0
        visibility = 0

        # Arrays to store waypoint data
        lat_lon_waypoints = []
        ele_waypoints = []
        hr_waypoints = []
        cad_waypoints = []
        power_waypoints = []
        vel_waypoints = []
        pace_waypoints = []

        # Array to store split summary info
        split_summary = []

        # Initialize variables to store previous latitude and longitude
        prev_latitude, prev_longitude = None, None

        # Initialize variables to store whether elevation, power, heart rate, cadence, and velocity are set
        is_elevation_set = False
        is_power_set = False
        is_heart_rate_set = False
        is_cadence_set = False
        is_velocity_set = False

        with open(file, "rb") as fit_file:
            fit_data = fitdecode.FitReader(fit_file)

            # Iterate over FIT messages
            for frame in fit_data:
                if isinstance(frame, fitdecode.FitDataMessage):
                    if frame.name == "session":
                        # Extract session data
                        (
                            initial_latitude,
                            initial_longitude,
                            activity_type,
                            first_waypoint_time,
                            total_elapsed_time,
                            total_timer_time,
                            calories,
                            distance,
                            avg_hr,
                            max_hr,
                            avg_cadence,
                            max_cadence,
                            avg_power,
                            max_power,
                            ele_gain,
                            ele_loss,
                            np,
                            avg_speed,
                            max_speed,
                            workout_feeling,
                            workout_rpe,
                        ) = parse_frame_session(frame)

                        # If initial latitude and longitude are set, use them to get city, town, and country
                        if (
                            initial_latitude is not None
                            and initial_longitude is not None
                        ):
                            # Use geocoding API to get city, town, and country based on coordinates
                            location_data = (
                                activities_utils.location_based_on_coordinates(
                                    initial_latitude, initial_longitude
                                )
                            )

                            # Extract city, town, and country from location data
                            if location_data:
                                city = location_data["city"]
                                town = location_data["town"]
                                country = location_data["country"]

                    # Extract activity name
                    if frame.name == "workout":
                        activity_name = parse_frame_workout(frame)

                    if frame.name == "split_summary" or frame.name == "unknown_313":
                        split_summary_split_type, split_summary_total_timer_time = parse_frame_split_summary(frame)

                        split_summary.append({"split_type": split_summary_split_type, "total_timer_time": split_summary_total_timer_time})

                    # Extract waypoint data
                    if frame.name == "record":
                        # Extract values from record frame
                        (
                            latitude,
                            longitude,
                            elevation,
                            time,
                            heart_rate,
                            cadence,
                            power,
                        ) = parse_frame_record(frame)

                        # Check elevation
                        if elevation is not None:
                            is_elevation_set = True

                        # Check if heart rate, cadence, power are set
                        if heart_rate is not None:
                            is_heart_rate_set = True

                        if cadence is not None:
                            is_cadence_set = True

                        if power is not None:
                            is_power_set = True

                        instant_speed = None
                        # Calculate instant speed, pace, and update waypoint arrays
                        if latitude is not None and longitude is not None:
                            instant_speed = activities_utils.calculate_instant_speed(
                                last_waypoint_time,
                                time,
                                latitude,
                                longitude,
                                prev_latitude,
                                prev_longitude,
                            )

                        # Calculate instance pace
                        instant_pace = None
                        if instant_speed:
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

                        append_if_not_none(ele_waypoints, timestamp, elevation, "ele")
                        append_if_not_none(hr_waypoints, timestamp, heart_rate, "hr")
                        append_if_not_none(cad_waypoints, timestamp, cadence, "cad")
                        append_if_not_none(power_waypoints, timestamp, power, "power")
                        append_if_not_none(
                            vel_waypoints, timestamp, instant_speed, "vel"
                        )
                        append_if_not_none(
                            pace_waypoints, timestamp, instant_pace, "pace"
                        )

                        # Update previous latitude, longitude, and last waypoint time
                        prev_latitude, prev_longitude, last_waypoint_time = (
                            latitude,
                            longitude,
                            time,
                        )

        # Calculate elevation gain/loss, pace, average speed, and average power
        if ele_gain is None and ele_loss is None:
            elevation_data = activities_utils.calculate_elevation_gain_loss(
                ele_waypoints
            )
            ele_gain = elevation_data["elevation_gain"]
            ele_loss = elevation_data["elevation_loss"]

        #pace = activities_utils.calculate_pace(
        #    distance, first_waypoint_time, last_waypoint_time
        #)
        total_timer_time, pace = calculate_pace(distance, total_timer_time, activity_type, split_summary)

        if avg_speed is None:
            avg_speed = activities_utils.calculate_average_speed(
                distance, first_waypoint_time, last_waypoint_time
            )

        if avg_power is None:
            avg_power = activities_utils.calculate_average_power(power_waypoints)

        # Create an Activity object with parsed data
        activity = activities_schema.Activity(
            user_id=user_id,
            name=activity_name,
            distance=distance,
            activity_type=activities_utils.define_activity_type(activity_type),
            start_time=first_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S"),
            end_time=last_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S"),
            total_elapsed_time=total_elapsed_time,
            total_timer_time=total_timer_time,
            city=city,
            town=town,
            country=country,
            elevation_gain=ele_gain,
            elevation_loss=ele_loss,
            pace=pace,
            average_speed=avg_speed,
            max_speed=max_speed,
            average_power=avg_power,
            max_power=max_power,
            normalized_power=np,
            average_hr=avg_hr,
            max_hr=max_hr,
            average_cad=avg_cadence,
            max_cad=max_cadence,
            workout_feeling=workout_feeling,
            workout_rpe=workout_rpe,
            calories=calories,
            visibility=visibility,
            strava_gear_id=None,
            strava_activity_id=None,
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
            "lat_lon_waypoints": lat_lon_waypoints,
            "prev_latitude": prev_latitude,
            "prev_longitude": prev_longitude,
        }
    except Exception as err:
        # Log the exception
        logger.error(f"Error in parse_fit_file: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Can't parse FIT file",
        ) from err


def parse_frame_session(frame):
    # Extracting coordinates
    initial_latitude = get_value_from_frame(frame, "start_position_lat")
    initial_longitude = get_value_from_frame(frame, "start_position_long")

    # Activity type logic
    activity_type = get_value_from_frame(frame, "sport", "Workout")
    sub_sport = get_value_from_frame(frame, "sub_sport")
    if sub_sport and sub_sport != "generic":
        if activity_type == "cycling" and sub_sport == "virtual_activity":
            activity_type = "virtual_ride"
        else:
            activity_type = sub_sport

    # Extracting time values
    start_time = get_value_from_frame(frame, "start_time")
    # total activity time
    total_elapsed_time = get_value_from_frame(frame, "total_elapsed_time")
    # total working time
    total_timer_time = get_value_from_frame(frame, "total_timer_time")

    # Extracting other values
    calories = get_value_from_frame(frame, "total_calories")
    distance = get_value_from_frame(frame, "total_distance")
    avg_hr = get_value_from_frame(frame, "avg_heart_rate")
    max_hr = get_value_from_frame(frame, "max_heart_rate")
    avg_cadence = get_value_from_frame(frame, "avg_cadence")
    max_cadence = get_value_from_frame(frame, "max_cadence")
    avg_power = get_value_from_frame(frame, "avg_power")
    max_power = get_value_from_frame(frame, "max_power")
    ele_gain = get_value_from_frame(frame, "total_ascent")
    ele_loss = get_value_from_frame(frame, "total_descent")
    np = get_value_from_frame(frame, "normalized_power")
    avg_speed = get_value_from_frame(frame, "enhanced_avg_speed")
    max_speed = get_value_from_frame(frame, "enhanced_max_speed")
    # Feeling after workout 0 to 100
    workout_feeling = get_value_from_frame(frame, "workout_feeling")
    # RPE (Rate of Perceived Exertion) scale from 10 to 100
    workout_rpe = get_value_from_frame(frame, "workout_rpe")

    initial_latitude, initial_longitude = convert_coordinates_to_degrees(
        initial_latitude, initial_longitude
    )

    # Return all extracted values
    return (
        initial_latitude,
        initial_longitude,
        activity_type,
        start_time,
        total_elapsed_time,
        total_timer_time,
        calories,
        distance,
        avg_hr,
        max_hr,
        avg_cadence,
        max_cadence,
        avg_power,
        max_power,
        ele_gain,
        ele_loss,
        np,
        avg_speed,
        max_speed,
        workout_feeling,
        workout_rpe,
    )


def parse_frame_workout(frame):
    # Extracting data using the helper function
    name = get_value_from_frame(frame, "wkt_name", "Workout")

    # Return the extracted name
    return name


def parse_frame_record(frame):
    # Extracting data using the helper function
    latitude = get_value_from_frame(frame, "position_lat")
    longitude = get_value_from_frame(frame, "position_long")
    elevation = get_value_from_frame(frame, "enhanced_altitude")
    time = get_value_from_frame(frame, "timestamp")
    if time:
        time = datetime.fromisoformat(time.strftime("%Y-%m-%dT%H:%M:%S"))
    heart_rate = get_value_from_frame(frame, "heart_rate")
    cadence = get_value_from_frame(frame, "cadence")
    power = get_value_from_frame(frame, "power")

    latitude, longitude = convert_coordinates_to_degrees(latitude, longitude)

    # Return all extracted values
    return latitude, longitude, elevation, time, heart_rate, cadence, power


def parse_frame_lap(frame):
    # start time
    start_time = get_value_from_frame(frame, "start_time")
    # total activity time
    total_elapsed_time = get_value_from_frame(frame, "total_elapsed_time")
    # total working time
    total_timer_time = get_value_from_frame(frame, "total_timer_time")
    # total distance
    distance = get_value_from_frame(frame, "total_distance")
    # speed values
    avg_speed = get_value_from_frame(frame, "enhanced_avg_speed")
    max_speed = get_value_from_frame(frame, "enhanced_max_speed")

    return (
        start_time,
        total_elapsed_time,
        total_timer_time,
        distance,
        avg_speed,
        max_speed,
    )


def parse_frame_split(frame):
    # split type
    split_type = get_value_from_frame(frame, "split_type")
    # total activity time
    total_elapsed_time = get_value_from_frame(frame, "total_elapsed_time")
    # total working time
    total_timer_time = get_value_from_frame(frame, "total_timer_time")
    # start time
    start_time = get_value_from_frame(frame, "start_time")
    # end time
    end_time = get_value_from_frame(frame, "end_time")

    return split_type, total_elapsed_time, total_timer_time, start_time, end_time


def parse_frame_split_summary(frame):
    # split type
    split_type = get_value_from_frame(frame, "split_type")
    if split_type is None:
        split_type = get_value_from_frame(frame, 0)
    # total working time
    total_timer_time = get_value_from_frame(frame, "total_timer_time")
    if total_timer_time is None:
        total_timer_time = get_value_from_frame(frame, 4)
        if total_timer_time is not None:
            total_timer_time = total_timer_time / 1000

    return split_type, total_timer_time


def get_value_from_frame(frame, key, default=None):
    try:
        value = frame.get_value(key)
        return value if value else default
    except KeyError:
        return default


def convert_coordinates_to_degrees(latitude, longitude):
    # Convert FIT coordinates to degrees if available
    if latitude is not None and longitude is not None:
        latitude = latitude * (180 / 2**31)
        longitude = longitude * (180 / 2**31)

    return latitude, longitude


def append_if_not_none(waypoint_list, time, value, key):
    if value is not None:
        waypoint_list.append({"time": time, key: value})


def calculate_pace(distance, total_timer_time, activity_type, split_summary):
    if activity_type != "lap_swimming":
        return total_timer_time, total_timer_time / distance
    else:
        time_active = 0
        for split in split_summary:
            if split["split_type"] != 4:
                time_active += split["total_timer_time"]

        return time_active, time_active / distance