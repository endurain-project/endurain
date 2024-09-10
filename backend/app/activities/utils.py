import logging
import os
import requests
import math

from fastapi import HTTPException, status, UploadFile

from typing import Union
from datetime import datetime
from urllib.parse import urlencode
from statistics import mean
from sqlalchemy.orm import Session


import activities.schema as activities_schema
import activities.crud as activities_crud

import activity_streams.crud as activity_streams_crud

import gpx.utils as gpx_utils
import fit.utils as fit_utils

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


async def parse_and_store_activity_from_file(
    token_user_id: int, file_path: str, db: Session
):
    try:
        # Get file extension
        _, file_extension = os.path.splitext(file_path)

        # Open the file and process it
        with open(file_path, "rb") as file:
            # Parse the file
            parsed_info = parse_file(token_user_id, file_extension, file_path)

            # Store the activity in the database
            created_activity = store_activity(parsed_info, db)

            # Return the created activity
            return created_activity
    except Exception as err:
        # Log the exception
        logger.error(
            f"Error in parse_and_store_activity_from_file: {err}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def parse_and_store_activity_from_uploaded_file(
    token_user_id: int, file: UploadFile, db: Session
):

    # Get file extension
    _, file_extension = os.path.splitext(file.filename)

    # Save the uploaded file in the 'uploads' directory
    with open(file.filename, "wb") as save_file:
        save_file.write(file.file.read())

    # Parse the file
    parsed_info = parse_file(token_user_id, file_extension, file.filename)

    # Store the activity in the database
    created_activity = store_activity(parsed_info, db)

    # Return the created activity
    return created_activity


def parse_file(token_user_id: int, file_extension: str, filename: str) -> dict:
    try:
        # Choose the appropriate parser based on file extension
        if file_extension.lower() == ".gpx":
            # Parse the GPX file
            parsed_info = gpx_utils.parse_gpx_file(filename, token_user_id)
        elif file_extension.lower() == ".fit":
            # Parse the FIT file
            parsed_info = fit_utils.parse_fit_file(filename, token_user_id)
        else:
            # file extension not supported raise an HTTPException with a 406 Not Acceptable status code
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail="File extension not supported. Supported file extensions are .gpx and .fit",
            )

        # Return the parsed information
        return parsed_info
    except Exception as err:
        # Log the exception
        logger.error(f"Error in parse_file: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
    finally:
        # Remove the file after processing
        os.remove(filename)


def store_activity(parsed_info: dict, db: Session):
    # create the activity in the database
    created_activity = activities_crud.create_activity(parsed_info["activity"], db)

    # Check if created_activity is None
    if created_activity is None:
        # raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating activity",
        )

    # Parse the activity streams from the parsed info
    activity_streams = gpx_utils.parse_activity_streams_from_gpx_file(
        parsed_info, created_activity.id
    )

    # Create activity streams in the database
    activity_streams_crud.create_activity_streams(activity_streams, db)

    # Return the created activity
    return created_activity


def calculate_activity_distances(activities: list[activities_schema.Activity]):
    """Calculate the distances of the activities for each type of activity (run, bike, swim)"""
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
        logger.error(
            f"Error in upload_file querying local from geocode: {err}",
            exc_info=True,
        )


def calculate_distance(lat1, lon1, lat2, lon2):

    # The radius of the Earth in meters (mean value)
    EARTH_RADIUS = 6371000  # 6,371 km = 6,371,000 meters

    # Convert latitude and longitude from degrees to radians
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    lat_diff = lat2_rad - lat1_rad
    lon_diff = lon2_rad - lon1_rad
    a = (
        math.sin(lat_diff / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(lon_diff / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # Calculate the distance
    distance = EARTH_RADIUS * c

    # Return the distance
    return distance


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
        distance = calculate_distance(
            prev_latitude, prev_longitude, latitude, longitude
        )

        # Calculate the instant speed in m/s
        instant_speed = distance / time_difference
    else:
        # If the time difference is not positive, return a default value
        instant_speed = 0

    # Return the instant speed
    return instant_speed


def calculate_elevation_gain_loss(waypoints):
    # Initialize the variables for the elevation gain and loss
    elevation_gain = 0
    elevation_loss = 0
    prev_elevation = None

    # Iterate over the waypoints and calculate the elevation gain and loss
    for waypoint in waypoints:
        # Get the elevation from the waypoint
        elevation = waypoint["ele"]

        # If prev_elevation is not None, calculate the elevation change
        if prev_elevation is not None:
            # Calculate the elevation change
            elevation_change = elevation - prev_elevation
            if elevation_change > 0:
                # If the elevation change is positive, add it to the elevation gain
                elevation_gain += elevation_change
            else:
                # If the elevation change is negative, add its absolute value to the elevation loss
                elevation_loss -= elevation_change

        # Update the prev_elevation variable
        prev_elevation = elevation

    # Return the elevation gain and loss
    return {"elevation_gain": elevation_gain, "elevation_loss": elevation_loss}


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


def calculate_average_speed(distance, first_waypoint_time, last_waypoint_time):
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

    if total_time_in_seconds == 0:
        # If the time difference is 0, return 0
        return 0

    # Calculate average speed in meters per second
    average_speed = distance / total_time_in_seconds

    # Return the average speed
    return average_speed


def calculate_average_power(waypoints):
    try:
        # Get the power values from the waypoints
        power_values = [float(waypoint["power"]) for waypoint in waypoints]
    except (ValueError, KeyError):
        # If there are no valid power values, return 0
        return 0

    if power_values:
        # Calculate the average power
        average_power = mean(power_values)

        # Return the average power
        return average_power
    else:
        # If there are no power values, return 0
        return 0


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
        "GravelRide": 5,
        "gravel_cycling": 5,
        "MountainBikeRide": 6,
        "mountain": 6,
        "VirtualRide": 7,
        "virtual_ride": 7,
        "Swim": 8,
        "swimming": 8,
        "open_water_swimming": 9,
        "open_water": 9,
        "Walk": 11,
        "walking": 11,
        "Hike": 12,
        "hiking": 12,
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
