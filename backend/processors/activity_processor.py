import logging
import os
import requests
import math

from datetime import datetime
from urllib.parse import urlencode
from statistics import mean

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def location_based_on_coordinates(latitude, longitude):
    """Get the location based on the coordinates using the geocode API.

    Args:
        latitude (float): The latitude coordinate.
        longitude (float): The longitude coordinate.

    Returns:
        dict: A dictionary containing the location information, including city, town, and country.
    """
    # Create a dictionary with the parameters for the request
    url_params = {
        "lat": latitude,
        "lon": longitude,
        "api_key=": os.environ.get("GEOCODES_MAPS_API"),
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


import math

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate the distance between two points on the Earth's surface using the Haversine formula.

    Args:
        lat1 (float): Latitude of the first point in degrees.
        lon1 (float): Longitude of the first point in degrees.
        lat2 (float): Latitude of the second point in degrees.
        lon2 (float): Longitude of the second point in degrees.

    Returns:
        float: The distance between the two points in meters.
    """
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
    """Calculate the instant speed based on two consecutive waypoints and their timestamps.

    Args:
        prev_time (datetime): The timestamp of the previous waypoint.
        time (datetime): The timestamp of the current waypoint.
        latitude (float): The latitude of the current waypoint.
        longitude (float): The longitude of the current waypoint.
        prev_latitude (float): The latitude of the previous waypoint.
        prev_longitude (float): The longitude of the previous waypoint.

    Returns:
        float: The calculated instant speed in meters per second.
    """
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
    """Calculate the elevation gain and loss based on the waypoints.

    Args:
        waypoints (list): A list of dictionaries representing the waypoints. Each dictionary should have an "ele" key representing the elevation.

    Returns:
        dict: A dictionary containing the elevation gain and loss. The keys are "elevation_gain" and "elevation_loss".
    """
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
    """Calculate the pace based on the distance and the time between two waypoints.

    Args:
        distance (float): The distance between two waypoints in meters.
        first_waypoint_time (datetime): The time of the first waypoint.
        last_waypoint_time (datetime): The time of the last waypoint.

    Returns:
        float: The pace in seconds per meter.
    """
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
    """Calculate the average speed based on the distance and the time between two waypoints.

    Args:
        distance (float): The distance between two waypoints in meters.
        first_waypoint_time (datetime): The timestamp of the first waypoint.
        last_waypoint_time (datetime): The timestamp of the last waypoint.

    Returns:
        float: The average speed in meters per second.
    """
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
    """
    Calculate the average power based on the power values in the waypoints.

    Parameters:
    - waypoints (list): A list of dictionaries representing waypoints, each containing a "power" key.

    Returns:
    - float: The average power calculated from the power values in the waypoints.
    """
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
    """Define the activity type based on the activity type string.

    Args:
        activity_type (str): The activity type string.

    Returns:
        int: The defined activity type.

    """
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
        "EBikeRide": 6,
        "VirtualRide": 7,
        "virtual_ride": 7,
        "swimming": 8,
        "open_water_swimming": 8,
        "Walk": 9,
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
