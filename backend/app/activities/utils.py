import os
import shutil
import requests
from geopy.distance import geodesic
import numpy as np
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status, UploadFile

from datetime import datetime
from urllib.parse import urlencode
from statistics import mean
from sqlalchemy.orm import Session
from sqlalchemy import func


import activities.schema as activities_schema
import activities.crud as activities_crud
import activities.models as activities_models

import activity_streams.crud as activity_streams_crud
import activity_streams.schema as activity_streams_schema

import gpx.utils as gpx_utils
import fit.utils as fit_utils

import core.logger as core_logger


def transform_schema_activity_to_model_activity(
    activity: activities_schema.Activity,
) -> activities_models.Activity:
    # Set the created date to now
    created_date = func.now()

    # If the created_at date is not None, set it to the created_date
    if activity.created_at is not None:
        created_date = activity.created_at

    # Create a new activity object
    new_activity = activities_models.Activity(
        user_id=activity.user_id,
        distance=activity.distance,
        name=activity.name,
        activity_type=activity.activity_type,
        start_time=activity.start_time,
        end_time=activity.end_time,
        timezone=activity.timezone,
        total_elapsed_time=activity.total_elapsed_time,
        total_timer_time=activity.total_timer_time,
        city=activity.city,
        town=activity.town,
        country=activity.country,
        created_at=created_date,
        elevation_gain=activity.elevation_gain,
        elevation_loss=activity.elevation_loss,
        pace=activity.pace,
        average_speed=activity.average_speed,
        max_speed=activity.max_speed,
        average_power=activity.average_power,
        max_power=activity.max_power,
        normalized_power=activity.normalized_power,
        average_hr=activity.average_hr,
        max_hr=activity.max_hr,
        average_cad=activity.average_cad,
        max_cad=activity.max_cad,
        workout_feeling=activity.workout_feeling,
        workout_rpe=activity.workout_rpe,
        calories=activity.calories,
        visibility=activity.visibility,
        gear_id=activity.gear_id,
        strava_gear_id=activity.strava_gear_id,
        strava_activity_id=activity.strava_activity_id,
        garminconnect_activity_id=activity.garminconnect_activity_id,
        garminconnect_gear_id=activity.garminconnect_gear_id,
    )

    return new_activity


def serialize_activity(activity: activities_schema.Activity):
    def make_aware_and_format(dt, timezone):
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(timezone).strftime("%Y-%m-%dT%H:%M:%S")

    timezone = (
        ZoneInfo(activity.timezone)
        if activity.timezone
        else ZoneInfo(os.environ.get("TZ"))
    )

    activity.start_time = make_aware_and_format(activity.start_time, timezone)
    activity.end_time = make_aware_and_format(activity.end_time, timezone)
    activity.created_at = make_aware_and_format(activity.created_at, timezone)

    return activity


def parse_and_store_activity_from_file(
    token_user_id: int,
    file_path: str,
    db: Session,
    from_garmin: bool = False,
    garminconnect_gear: dict = None,
):
    try:
        # Get file extension
        _, file_extension = os.path.splitext(file_path)
        garmin_connect_activity_id = None

        if from_garmin:
            garmin_connect_activity_id = os.path.basename(file_path).split("_")[0]

        # Open the file and process it
        with open(file_path, "rb"):
            # Parse the file
            parsed_info = parse_file(token_user_id, file_extension, file_path)

            if parsed_info is not None:
                created_activities = []
                idsToFileName = ""
                if file_extension.lower() == ".gpx":
                    # Store the activity in the database
                    created_activity = store_activity(parsed_info, db)
                    created_activities.append(created_activity)
                    idsToFileName = idsToFileName + str(created_activity.id)
                elif file_extension.lower() == ".fit":
                    # Split the records by activity (check for multiple activities in the file)
                    split_records_by_activity = fit_utils.split_records_by_activity(
                        parsed_info
                    )

                    # Create activity objects for each activity in the file
                    if from_garmin:
                        created_activities_objects = fit_utils.create_activity_objects(
                            split_records_by_activity,
                            token_user_id,
                            int(garmin_connect_activity_id),
                            garminconnect_gear,
                            db,
                        )
                    else:
                        created_activities_objects = fit_utils.create_activity_objects(
                            split_records_by_activity, token_user_id
                        )

                    for activity in created_activities_objects:
                        # Store the activity in the database
                        created_activity = store_activity(activity, db)
                        created_activities.append(created_activity)

                    for index, activity in enumerate(created_activities):
                        idsToFileName += str(activity.id)  # Add the id to the string
                        # Add an underscore if it's not the last item
                        if index < len(created_activities) - 1:
                            idsToFileName += (
                                "_"  # Add an underscore if it's not the last item
                            )

                # Define the directory where the processed files will be stored
                processed_dir = "files/processed"

                # Define new file path with activity ID as filename
                new_file_name = f"{idsToFileName}{file_extension}"

                # Move the file to the processed directory
                move_file(processed_dir, new_file_name, file_path)

                # Return the created activity
                return created_activities
            else:
                return None
    except HTTPException:
        pass
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in parse_and_store_activity_from_file - {str(err)}", "error"
        )


def parse_and_store_activity_from_uploaded_file(
    token_user_id: int, file: UploadFile, db: Session
):

    # Get file extension
    _, file_extension = os.path.splitext(file.filename)

    try:
        # Ensure the 'files' directory exists
        upload_dir = "files"
        os.makedirs(upload_dir, exist_ok=True)

        # Build the full path where the file will be saved
        file_path = os.path.join(upload_dir, file.filename)

        # Save the uploaded file in the 'files' directory
        with open(file_path, "wb") as save_file:
            save_file.write(file.file.read())

        # Parse the file
        parsed_info = parse_file(token_user_id, file_extension, file_path)

        if parsed_info is not None:
            created_activities = []
            idsToFileName = ""
            if file_extension.lower() == ".gpx":
                # Store the activity in the database
                created_activity = store_activity(parsed_info, db)
                created_activities.append(created_activity)
                idsToFileName = idsToFileName + str(created_activity.id)
            elif file_extension.lower() == ".fit":
                # Split the records by activity (check for multiple activities in the file)
                split_records_by_activity = fit_utils.split_records_by_activity(
                    parsed_info
                )

                # Create activity objects for each activity in the file
                created_activities_objects = fit_utils.create_activity_objects(
                    split_records_by_activity, token_user_id
                )

                for activity in created_activities_objects:
                    # Store the activity in the database
                    created_activity = store_activity(activity, db)
                    created_activities.append(created_activity)

                for index, activity in enumerate(created_activities):
                    idsToFileName += str(activity.id)  # Add the id to the string
                    # Add an underscore if it's not the last item
                    if index < len(created_activities) - 1:
                        idsToFileName += (
                            "_"  # Add an underscore if it's not the last item
                        )

            # Define the directory where the processed files will be stored
            processed_dir = "files/processed"

            # Define new file path with activity ID as filename
            new_file_name = f"{idsToFileName}{file_extension}"

            # Move the file to the processed directory
            move_file(processed_dir, new_file_name, file_path)

            for activity in created_activities:
                # Serialize the activity
                activity = serialize_activity(activity)

            # Return the created activity
            return created_activities
        else:
            return None
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in parse_and_store_activity_from_uploaded_file - {str(err)}",
            "error",
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(err)}",
        ) from err


def move_file(new_dir: str, new_filename: str, file_path: str):
    try:
        # Ensure the new directory exists
        os.makedirs(new_dir, exist_ok=True)

        # Define the new file path
        new_file_path = os.path.join(new_dir, new_filename)

        # Move the file
        shutil.move(file_path, new_file_path)
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in move_file - {str(err)}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(err)}",
        ) from err


def parse_file(token_user_id: int, file_extension: str, filename: str) -> dict:
    try:
        if filename.lower() != "bulk_import/__init__.py":
            core_logger.print_to_log(f"Parsing file: {filename}")
            # Choose the appropriate parser based on file extension
            if file_extension.lower() == ".gpx":
                # Parse the GPX file
                parsed_info = gpx_utils.parse_gpx_file(filename, token_user_id)
            elif file_extension.lower() == ".fit":
                # Parse the FIT file
                parsed_info = fit_utils.parse_fit_file(filename)
            else:
                # file extension not supported raise an HTTPException with a 406 Not Acceptable status code
                raise HTTPException(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    detail="File extension not supported. Supported file extensions are .gpx and .fit",
                )

            return parsed_info
        else:
            return None
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in parse_file - {str(err)}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(err)}",
        ) from err


def store_activity(parsed_info: dict, db: Session):
    # create the activity in the database
    created_activity = activities_crud.create_activity(parsed_info["activity"], db)

    # Check if created_activity is None
    if created_activity is None:
        # Log the error
        core_logger.print_to_log(
            "Error in store_activity - activity is None, error creating activity",
            "error",
        )
        # raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating activity",
        )

    # Parse the activity streams from the parsed info
    activity_streams = parse_activity_streams_from_file(
        parsed_info, created_activity.id
    )

    # Create activity streams in the database
    activity_streams_crud.create_activity_streams(activity_streams, db)

    # Return the created activity
    return created_activity


def parse_activity_streams_from_file(parsed_info: dict, activity_id: int):
    # Create a dictionary mapping stream types to is_set keys and waypoints keys
    stream_mapping = {
        1: ("is_heart_rate_set", "hr_waypoints"),
        2: ("is_power_set", "power_waypoints"),
        3: ("is_cadence_set", "cad_waypoints"),
        4: ("is_elevation_set", "ele_waypoints"),
        5: ("is_velocity_set", "vel_waypoints"),
        6: ("is_velocity_set", "pace_waypoints"),
        7: ("is_lat_lon_set", "lat_lon_waypoints"),
    }

    # Create a list of tuples containing stream type, is_set, and waypoints
    stream_data_list = [
        (
            stream_type,
            (
                is_set_key(parsed_info)
                if callable(is_set_key)
                else parsed_info[is_set_key]
            ),
            parsed_info[waypoints_key],
        )
        for stream_type, (is_set_key, waypoints_key) in stream_mapping.items()
        if (
            is_set_key(parsed_info) if callable(is_set_key) else parsed_info[is_set_key]
        )
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


def calculate_activity_distances(activities: list[activities_schema.Activity]):
    # Initialize the distances
    run = bike = swim = 0.0

    if activities is not None:
        # Calculate the distances
        for activity in activities:
            if activity.activity_type in [1, 2, 3]:
                run += activity.distance
            elif activity.activity_type in [4, 5, 6, 7]:
                bike += activity.distance
            elif activity.activity_type in [8, 9]:
                swim += activity.distance

    # Return the distances
    return activities_schema.ActivityDistances(run=run, bike=bike, swim=swim)


def location_based_on_coordinates(latitude, longitude) -> dict | None:
    if latitude is None or longitude is None:
        return None

    if os.environ.get("GEOCODES_MAPS_API") == "changeme":
        return None

    # Create a dictionary with the parameters for the request
    url_params = {
        "lat": latitude,
        "lon": longitude,
        "api_key": os.environ.get("GEOCODES_MAPS_API"),
    }

    # Create the URL for the request
    url = f"https://geocode.maps.co/reverse?{urlencode(url_params)}"

    # Make the request and get the response
    try:
        # Make the request and get the response
        response = requests.get(url)
        response.raise_for_status()

        # Get the data from the response
        data = response.json().get("address", {})

        # Return the data
        return {
            "city": data.get("city"),
            "town": data.get("town"),
            "country": data.get("country"),
        }
    except requests.exceptions.RequestException as err:
        # Log the error
        core_logger.print_to_log_and_console(
            f"Error in location_based_on_coordinates - {str(err)}", "error"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Error in location_based_on_coordinates: {str(err)}",
        )


def append_if_not_none(waypoint_list, time, value, key):
    if value is not None:
        waypoint_list.append({"time": time, key: value})


def calculate_instant_speed(
    prev_time, time, latitude, longitude, prev_latitude, prev_longitude
):
    # Convert the time strings to datetime objects
    time_calc = datetime.fromisoformat(time.strftime("%Y-%m-%dT%H:%M:%S"))

    # If prev_time is None, return a default value
    if prev_time is None:
        return 0

    # Convert the time strings to datetime objects
    prev_time_calc = datetime.fromisoformat(prev_time.strftime("%Y-%m-%dT%H:%M:%S"))

    # Calculate the time difference in seconds
    time_difference = (time_calc - prev_time_calc).total_seconds()

    # If the time difference is positive, calculate the instant speed
    if time_difference > 0:
        # Calculate the distance in meters
        distance = geodesic(
            (prev_latitude, prev_longitude), (latitude, longitude)
        ).meters

        # Calculate the instant speed in m/s
        instant_speed = distance / time_difference
    else:
        # If the time difference is not positive, return a default value
        instant_speed = 0

    # Return the instant speed
    return instant_speed


def calculate_elevation_gain_loss(waypoints):
    try:
        # Get the values from the waypoints
        values = [float(waypoint["ele"]) for waypoint in waypoints]
    except (ValueError, KeyError):
        # If there are no valid values, return 0
        return 0, 0

    elevation_gain = 0
    elevation_loss = 0

    # Iterate over the elevation data, comparing consecutive points
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]

        if diff > 0:
            elevation_gain += diff  # If elevation increases, add to gain
        elif diff < 0:
            elevation_loss += abs(diff)  # If elevation decreases, add to loss

    return elevation_gain, elevation_loss


def calculate_pace(distance, first_waypoint_time, last_waypoint_time):
    # If the distance is 0, return 0
    if distance == 0:
        return 0

    # Convert the time strings to datetime objects
    start_datetime = datetime.fromisoformat(
        first_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S")
    )
    end_datetime = datetime.fromisoformat(
        last_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S")
    )

    # Calculate the time difference in seconds
    total_time_in_seconds = (end_datetime - start_datetime).total_seconds()

    # Calculate pace in seconds per meter
    pace_seconds_per_meter = total_time_in_seconds / distance

    # Return the pace
    return pace_seconds_per_meter


def calculate_avg_and_max(data, type):
    try:
        # Get the values from the data
        values = [
            float(waypoint[type]) for waypoint in data if waypoint.get(type) is not None
        ]
    except (ValueError, KeyError):
        # If there are no valid values, return 0
        return 0, 0

    # Calculate the average and max values
    avg_value = mean(values)
    max_value = max(values)

    return avg_value, max_value


def calculate_np(data):
    try:
        # Get the power values from the data
        values = [
            float(waypoint["power"])
            for waypoint in data
            if waypoint["power"] is not None
        ]
    except:
        # If there are no valid values, return 0
        return 0

    # Calculate the fourth power of each power value
    fourth_powers = [p**4 for p in values]

    # Calculate the average of the fourth powers
    avg_fourth_power = sum(fourth_powers) / len(fourth_powers)

    # Take the fourth root of the average of the fourth powers to get Normalized Power
    normalized_power = avg_fourth_power ** (1 / 4)

    return normalized_power


def define_activity_type(activity_type):
    # Default value
    auxType = 10

    # Define the mapping for the activity types
    type_mapping = {
        "Run": 1,
        "running": 1,
        "trail running": 2,
        "TrailRun": 2,
        "VirtualRun": 3,
        "cycling": 4,
        "Ride": 4,
        "road": 4,
        "GravelRide": 5,
        "gravel_cycling": 5,
        "MountainBikeRide": 6,
        "mountain": 6,
        "VirtualRide": 7,
        "virtual_ride": 7,
        "Swim": 8,
        "swimming": 8,
        "lap_swimming": 8,
        "open_water_swimming": 9,
        "open_water": 9,
        "Walk": 11,
        "walking": 11,
        "Hike": 12,
        "hiking": 12,
        "Rowing": 13,
        "indoor_rowing": 13,
        "yoga": 14,
        "Yoga": 14,
        "AlpineSki": 15,
        "resort_skiing": 15,
        "alpine_skiing": 15,
        "NordicSki": 16,
        "Snowboard": 17,
    }
    # "AlpineSki",
    # "BackcountrySki",
    # "Badminton",
    # "Canoeing",
    # "Crossfit",
    # "EBikeRide",
    # "Elliptical",
    # "EMountainBikeRide",
    # "Golf",
    # "GravelRide",
    # "Handcycle",
    # "HighIntensityIntervalTraining",
    # "Hike",
    # "IceSkate",
    # "InlineSkate",
    # "Kayaking",
    # "Kitesurf",
    # "MountainBikeRide",
    # "NordicSki",
    # "Pickleball",
    # "Pilates",
    # "Racquetball",
    # "Ride",
    # "RockClimbing",
    # "RollerSki",
    # "Rowing",
    # "Run",
    # "Sail",
    # "Skateboard",
    # "Snowboard",
    # "Snowshoe",
    # "Soccer",
    # "Squash",
    # "StairStepper",
    # "StandUpPaddling",
    # "Surfing",
    # "Swim",
    # "TableTennis",
    # "Tennis",
    # "TrailRun",
    # "Velomobile",
    # "VirtualRide",
    # "VirtualRow",
    # "VirtualRun",
    # "Walk",
    # "WeightTraining",
    # "Wheelchair",
    # "Windsurf",
    # "Workout",
    # "Yoga"

    # Get the activity type from the mapping
    auxType = type_mapping.get(activity_type, 10)

    # Return the activity type
    return auxType
