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
    stream_data_list = [
        (1, parsed_info["is_heart_rate_set"], parsed_info["hr_waypoints"]),
        (2, parsed_info["is_power_set"], parsed_info["power_waypoints"]),
        (3, parsed_info["is_cadence_set"], parsed_info["cad_waypoints"]),
        (4, parsed_info["is_elevation_set"], parsed_info["ele_waypoints"]),
        (5, parsed_info["is_velocity_set"], parsed_info["vel_waypoints"]),
        (6, parsed_info["is_velocity_set"], parsed_info["pace_waypoints"]),
        (
            7,
            parsed_info["prev_latitude"] is not None
            and parsed_info["prev_longitude"] is not None,
            parsed_info["lat_lon_waypoints"],
        ),
    ]

    # Filter the list to include only those with is_set True
    stream_data_list = [
        (stream_type, is_set, waypoints)
        for stream_type, is_set, waypoints in stream_data_list
        if is_set
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
        fit_data = fitdecode.FitReader(open(file, "rb"))

        # Initialize default values for various variables
        activity_name = "Workout"
        activity_type = "Workout"
        distance = 0
        first_waypoint_time = None
        last_waypoint_time = None
        city = None
        town = None
        country = None
        process_one_time_fields = 0
        pace = 0
        calories = 0
        visibility = 0

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
        is_elevation_set = False
        is_power_set = False
        is_heart_rate_set = False
        is_cadence_set = False
        is_velocity_set = False

        # Iterate over FIT messages
        for frame in fit_data:
            if isinstance(frame, fitdecode.FitDataMessage):
                if frame.name == "session":
                    # Extract calories
                    try:
                        calories = (
                            frame.get_value("total_calories")
                            if frame.get_value("total_calories")
                            else None
                        )
                    except KeyError:
                        calories = 0
                    
                    # Extract activity type from sport field
                    try:
                        activity_type = (
                            frame.get_value("sport")
                            if frame.get_value("sport")
                            else "Workout"
                        )
                        # Extract sub-sport
                        if (
                            frame.get_value("sub_sport")
                            and frame.get_value("sub_sport") != "generic"
                        ):
                            if(activity_type == "cycling"):
                                if(frame.get_value("sub_sport") == "virtual_activity"):
                                    activity_type = "virtual_ride"
                                else:
                                    activity_type = frame.get_value("sub_sport")
                            else:
                                activity_type = frame.get_value("sub_sport")
                    except KeyError:
                        activity_type = "Workout"
                # Extract activity name
                if frame.name == "workout":
                    activity_name = (
                        frame.get_value("wkt_name")
                        if frame.get_value("wkt_name")
                        else "Workout"
                    )

                # Extract waypoint data
                if frame.name == "record":
                    # for field in frame.fields:
                    # print(f"{field.name}: {field.value}")
                    # Extract latitude and longitude
                    latitude = frame.get_value("position_lat") or 0
                    longitude = frame.get_value("position_long") or 0

                    # Extract elevation
                    try:
                        elevation = frame.get_value("enhanced_altitude")
                    except KeyError:
                        elevation = 0
                    
                    # Extract timestamp
                    time = (
                        datetime.fromisoformat(
                            frame.get_value("timestamp").strftime("%Y-%m-%dT%H:%M:%S")
                        )
                        if frame.get_value("timestamp")
                        else ""
                    )

                    # Extract heart rate
                    try:
                        heart_rate = frame.get_value("heart_rate")
                    except KeyError:
                        heart_rate = 0

                    # Extract cadence
                    try:
                        cadence = frame.get_value("cadence")
                    except KeyError:
                        cadence = 0

                    # Extract power
                    try:
                        power = frame.get_value("power")
                    except KeyError:
                        power = 0

                    # Convert FIT coordinates to degrees if available
                    if latitude is not None and longitude is not None:
                        latitude = latitude * (180 / 2**31)
                        longitude = longitude * (180 / 2**31)

                    if prev_latitude is not None and prev_longitude is not None and latitude != 0 and longitude != 0 and prev_latitude != 0 and prev_longitude != 0:
                        distance += activities_utils.calculate_distance(
                            prev_latitude, prev_longitude, latitude, longitude
                        )

                    # Check elevation
                    if elevation is not None and elevation != 0:
                        is_elevation_set = True

                    if first_waypoint_time is None:
                        first_waypoint_time = time

                    if process_one_time_fields == 0 and latitude and longitude:
                        # Use geocoding API to get city, town, and country based on coordinates
                        location_data = activities_utils.location_based_on_coordinates(
                            latitude, longitude
                        )
                        city = location_data["city"]
                        town = location_data["town"]
                        country = location_data["country"]

                        process_one_time_fields = 1

                    # Check if heart rate, cadence, power are set
                    if heart_rate != 0:
                        is_heart_rate_set = True

                    if cadence != 0:
                        is_cadence_set = True

                    if power != 0:
                        is_power_set = True

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
                        is_velocity_set = True

                    # Append waypoint data to respective arrays
                    if latitude is not None and longitude is not None:
                        lat_lon_waypoints.append(
                            {
                                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "lat": latitude,
                                "lon": longitude,
                            }
                        )

                    if elevation is not None:
                        ele_waypoints.append(
                            {
                                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "ele": elevation,
                            }
                        )

                    if heart_rate is not None:
                        hr_waypoints.append(
                            {
                                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "hr": heart_rate,
                            }
                        )

                    if cadence is not None:
                        cad_waypoints.append(
                            {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "cad": cadence}
                        )

                    if power is not None:
                        power_waypoints.append(
                            {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "power": power}
                        )

                    if instant_speed is not None and instant_speed != 0:
                        vel_waypoints.append(
                            {
                                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "vel": instant_speed,
                            }
                        )

                    if instant_pace != 0:
                        pace_waypoints.append(
                            {
                                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "pace": instant_pace,
                            }
                        )

                    # Update previous latitude, longitude, and last waypoint time
                    prev_latitude, prev_longitude, last_waypoint_time = (
                        latitude,
                        longitude,
                        time,
                    )

        # Calculate elevation gain/loss, pace, average speed, and average power
        elevation_data = activities_utils.calculate_elevation_gain_loss(ele_waypoints)
        elevation_gain = elevation_data["elevation_gain"]
        elevation_loss = elevation_data["elevation_loss"]
        pace = activities_utils.calculate_pace(
            distance, first_waypoint_time, last_waypoint_time
        )

        average_speed = activities_utils.calculate_average_speed(
            distance, first_waypoint_time, last_waypoint_time
        )

        average_power = activities_utils.calculate_average_power(power_waypoints)

        # Create an Activity object with parsed data
        activity = activities_schema.Activity(
            user_id=user_id,
            name=activity_name,
            distance=distance,
            activity_type=activities_utils.define_activity_type(activity_type),
            start_time=first_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S"),
            end_time=last_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S"),
            city=city,
            town=town,
            country=country,
            elevation_gain=elevation_gain,
            elevation_loss=elevation_loss,
            pace=pace,
            average_speed=average_speed,
            average_power=average_power,
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
