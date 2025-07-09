import os
import shutil
import requests
import statistics
from geopy.distance import geodesic
import numpy as np
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status, UploadFile

from datetime import datetime
from urllib.parse import urlencode
from statistics import mean
from sqlalchemy.orm import Session
from sqlalchemy import func

import activities.activity.schema as activities_schema
import activities.activity.crud as activities_crud
import activities.activity.models as activities_models

import users.user.crud as users_crud

import users.user_privacy_settings.crud as users_privacy_settings_crud
import users.user_privacy_settings.schema as users_privacy_settings_schema

import activities.activity_laps.crud as activity_laps_crud

import activities.activity_sets.crud as activity_sets_crud

import activities.activity_streams.crud as activity_streams_crud
import activities.activity_streams.schema as activity_streams_schema

import activities.activity_workout_steps.crud as activity_workout_steps_crud

import gpx.utils as gpx_utils
import fit.utils as fit_utils

import core.logger as core_logger
import core.config as core_config

# Global Activity Type Mappings (ID to Name)
ACTIVITY_ID_TO_NAME = {
    1: "Run",
    2: "Trail run",
    3: "Virtual run",
    4: "Ride",
    5: "Gravel ride",
    6: "MTB ride",
    7: "Virtual ride",
    8: "Lap swimming",
    9: "Open water swimming",
    10: "Workout",
    11: "Walk",
    12: "Hike",
    13: "Rowing",
    14: "Yoga",
    15: "Alpine ski",
    16: "Nordic ski",
    17: "Snowboard",
    18: "Transition",
    19: "Strength training",
    20: "Crossfit",
    21: "Tennis",
    22: "TableTennis",
    23: "Badminton",
    24: "Squash",
    25: "Racquetball",
    26: "Pickleball",
    27: "Commuting ride",
    28: "Indoor ride",
    29: "Mixed surface ride"  # Added based on define_activity_type
    # Add other mappings as needed based on the full list in define_activity_type comments if required
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
}

# Global Activity Type Mappings (Name to ID) - Case Insensitive Keys
ACTIVITY_NAME_TO_ID = {name.lower(): id for id, name in ACTIVITY_ID_TO_NAME.items()}
# Add specific variations found in define_activity_type
ACTIVITY_NAME_TO_ID.update(
    {
        "running": 1,
        "trail running": 2,
        "trailrun": 2,
        "virtualrun": 3,
        "cycling": 4,
        "road": 4,
        "gravelride": 5,
        "gravel_cycling": 5,
        "mountainbikeride": 6,
        "mountain": 6,
        "virtualride": 7,
        "virtual_ride": 7,
        "swim": 8,
        "swimming": 8,
        "lap_swimming": 8,
        "open_water_swimming": 9,
        "open_water": 9,
        "walk": 11,
        "walking": 11,
        "hike": 12,
        "hiking": 12,
        "rowing": 13,
        "indoor_rowing": 13,
        "yoga": 14,
        "alpineski": 15,
        "resort_skiing": 15,
        "alpine_skiing": 15,
        "nordicski": 16,
        "snowboard": 17,
        "transition": 18,
        "strength_training": 19,
        "weighttraining": 19,
        "crossfit": 20,
        "tennis": 21,
        "tabletennis": 22,
        "badminton": 23,
        "squash": 24,
        "racquetball": 25,
        "pickleball": 26,
        "commuting_ride": 27,
        "indoor_ride": 28,
        "mixed_surface_ride": 29,
    }
)


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
        description=activity.description,
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
        hide_start_time=activity.hide_start_time,
        hide_location=activity.hide_location,
        hide_map=activity.hide_map,
        hide_hr=activity.hide_hr,
        hide_power=activity.hide_power,
        hide_cadence=activity.hide_cadence,
        hide_elevation=activity.hide_elevation,
        hide_speed=activity.hide_speed,
        hide_pace=activity.hide_pace,
        hide_laps=activity.hide_laps,
        hide_workout_sets_steps=activity.hide_workout_sets_steps,
        hide_gear=activity.hide_gear,
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
        else ZoneInfo(os.environ.get("TZ", "UTC"))
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
            user = users_crud.get_user_by_id(token_user_id, db)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

            user_privacy_settings = (
                users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                    user.id, db
                )
            )

            # Parse the file
            parsed_info = parse_file(
                token_user_id,
                user_privacy_settings,
                file_extension,
                file_path,
                db,
            )

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
                            user_privacy_settings,
                            int(garmin_connect_activity_id),
                            garminconnect_gear,
                            db,
                        )
                    else:
                        created_activities_objects = fit_utils.create_activity_objects(
                            split_records_by_activity,
                            token_user_id,
                            user_privacy_settings,
                            None,
                            None,
                            db,
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
                else:
                    core_logger.print_to_log_and_console(
                        f"File extension not supported: {file_extension}", "error"
                    )
                # Define the directory where the processed files will be stored
                processed_dir = core_config.FILES_PROCESSED_DIR

                # Define new file path with activity ID as filename
                new_file_name = f"{idsToFileName}{file_extension}"

                # Move the file to the processed directory
                move_file(processed_dir, new_file_name, file_path)

                # Return the created activity
                return created_activities
            else:
                return None
    except HTTPException as http_err:
        raise http_err
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
        upload_dir = core_config.FILES_DIR
        os.makedirs(upload_dir, exist_ok=True)

        # Build the full path where the file will be saved
        file_path = os.path.join(upload_dir, file.filename)

        # Save the uploaded file in the 'files' directory
        with open(file_path, "wb") as save_file:
            save_file.write(file.file.read())

        user = users_crud.get_user_by_id(token_user_id, db)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user_privacy_settings = (
            users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                user.id, db
            )
        )

        # Parse the file
        parsed_info = parse_file(
            token_user_id,
            user_privacy_settings,
            file_extension,
            file_path,
            db,
        )

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
                    split_records_by_activity,
                    token_user_id,
                    user_privacy_settings,
                    None,
                    None,
                    db,
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
            else:
                core_logger.print_to_log_and_console(
                    f"File extension not supported: {file_extension}", "error"
                )

            # Define the directory where the processed files will be stored
            processed_dir = core_config.FILES_PROCESSED_DIR

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
            exc=err,
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


def parse_file(
    token_user_id: int,
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettings,
    file_extension: str,
    filename: str,
    db: Session,
) -> dict:
    try:
        if filename.lower() != "bulk_import/__init__.py":
            core_logger.print_to_log(f"Parsing file: {filename}")
            # Choose the appropriate parser based on file extension
            if file_extension.lower() == ".gpx":
                # Parse the GPX file
                parsed_info = gpx_utils.parse_gpx_file(
                    filename,
                    token_user_id,
                    user_privacy_settings,
                    db,
                )
            elif file_extension.lower() == ".fit":
                # Parse the FIT file
                parsed_info = fit_utils.parse_fit_file(filename, db)
            else:
                # file extension not supported raise an HTTPException with a 406 Not Acceptable status code
                raise HTTPException(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    detail="File extension not supported. Supported file extensions are .gpx and .fit",
                )
                return None  # Can't return parsed info if we haven't parsed anything
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

    if activity_streams is not None:
        # Create activity streams in the database
        activity_streams_crud.create_activity_streams(activity_streams, db)

    if parsed_info.get("laps") is not None:
        # Create activity laps in the database
        activity_laps_crud.create_activity_laps(
            parsed_info["laps"], created_activity.id, db
        )

    if parsed_info.get("workout_steps") is not None:
        # Create activity workout steps in the database
        activity_workout_steps_crud.create_activity_workout_steps(
            parsed_info["workout_steps"], created_activity.id, db
        )

    if parsed_info.get("sets") is not None:
        # Create activity sets in the database
        activity_sets_crud.create_activity_sets(
            parsed_info["sets"], created_activity.id, db
        )

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
    run = bike = swim = walk = hike = rowing = snow_ski = snowboard = 0.0

    if activities is not None:
        # Calculate the distances
        for activity in activities:
            if activity.activity_type in [1, 2, 3]:
                run += activity.distance
            elif activity.activity_type in [4, 5, 6, 7, 27, 28, 29]:
                bike += activity.distance
            elif activity.activity_type in [8, 9]:
                swim += activity.distance
            elif activity.activity_type in [11]:
                walk += activity.distance
            elif activity.activity_type in [12]:
                hike += activity.distance
            elif activity.activity_type in [13]:
                rowing += activity.distance
            elif activity.activity_type in [15, 16]:
                snow_ski += activity.distance
            elif activity.activity_type in [17]:
                snowboard += activity.distance

    # Return the distances
    return activities_schema.ActivityDistances(
        run=run,
        bike=bike,
        swim=swim,
        walk=walk,
        hike=hike,
        rowing=rowing,
        snow_ski=snow_ski,
        snowboard=snowboard,
    )


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


def compute_elevation_gain_and_loss(
    elevations, median_window=6, avg_window=3, threshold=0.1
):
    # 1) Median Filter
    def median_filter(values, window_size):
        if window_size < 2:
            return values[:]
        half = window_size // 2
        filtered = []
        for i in range(len(values)):
            start = max(0, i - half)
            end = min(len(values), i + half + 1)
            window_vals = values[start:end]
            m = statistics.median(window_vals)
            filtered.append(m)
        return filtered

    # 2) Moving-Average Smoothing
    def moving_average(values, window_size):
        if window_size < 2:
            return values[:]
        half = window_size // 2
        smoothed = []
        n = len(values)
        for i in range(n):
            start = max(0, i - half)
            end = min(n, i + half + 1)
            window_vals = values[start:end]
            smoothed.append(statistics.mean(window_vals))
        return smoothed

    try:
        # Get the values from the elevations
        values = [float(waypoint["ele"]) for waypoint in elevations]
    except (ValueError, KeyError):
        # If there are no valid values, return 0
        return 0, 0

    # Apply median filter -> then average smoothing
    filtered = median_filter(values, median_window)
    filtered = moving_average(filtered, avg_window)

    # 3) Compute gain/loss with threshold
    total_gain = 0.0
    total_loss = 0.0
    for i in range(1, len(filtered)):
        diff = filtered[i] - filtered[i - 1]
        if diff > threshold:
            total_gain += diff
        elif diff < -threshold:
            total_loss -= diff  # diff is negative, so subtracting it is adding positive
    return total_gain, total_loss


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


def define_activity_type(activity_type_name: str) -> int:
    """
    Maps an activity type name (string) to its corresponding ID (integer).
    Uses the global ACTIVITY_NAME_TO_ID dictionary.
    Returns 10 (Workout) if the name is not found.
    """
    # Default value
    default_type_id = 10

    # Get the activity type ID from the global mapping (case-insensitive)
    # Ensure input is a string before lowercasing
    if isinstance(activity_type_name, str):
        return ACTIVITY_NAME_TO_ID.get(activity_type_name.lower(), default_type_id)
    else:
        # Handle non-string input if necessary, or return default
        return default_type_id


def set_activity_name_based_on_activity_type(activity_type_id: int) -> str:
    """
    Maps an activity type ID (integer) to its corresponding name (string).
    Uses the global ACTIVITY_ID_TO_NAME dictionary.
    Returns "Workout" if the ID is not found or is 10.
    Appends " workout" suffix if the name is not "Workout".
    """
    # Get the mapping for the activity type ID, default to "Workout"
    mapping = ACTIVITY_ID_TO_NAME.get(activity_type_id, "Workout")

    # If type is not 10 (Workout), return the mapping with " workout" suffix
    return mapping + " workout" if mapping != "Workout" else mapping
