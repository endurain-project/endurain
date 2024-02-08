import logging

from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client
from concurrent.futures import ThreadPoolExecutor
from pint import Quantity

from schemas import schema_activities, schema_activity_streams
from crud import crud_user_integrations, crud_activities, crud_activity_streams
from processors import activity_processor

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def get_user_strava_activities_by_days(start_date: datetime, user_id: int, db: Session):
    # Get the user integrations by user ID
    user_integrations = crud_user_integrations.get_user_integrations_by_user_id(
        user_id, db
    )

    # Check if user integrations is None
    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User information not found",
        )

    # Check if user_integrations.strava_token_expires_at is None
    if user_integrations.strava_token_expires_at is None:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Strava access token not found",
        )

    # Log the start of the activities processing
    logger.info(f"User {user_id}: Started activities processing")

    # Create a Strava client with the user's access token
    strava_client = Client(access_token=user_integrations.strava_token)

    # Fetch Strava activities after the specified start date
    strava_activities = list(strava_client.get_activities(after=start_date))

    if strava_activities is None:
        # Log an informational event if no activities were found
        logger.info(
            f"User {user_id}: No new activities found after {start_date}: strava_activities is None"
        )

    # Use ThreadPoolExecutor for parallel processing of activities
    with ThreadPoolExecutor() as executor:
        executor.map(
            lambda activity: process_activity(activity, user_id, strava_client, db),
            strava_activities,
        )

    # Log an informational event for tracing
    logger.info(f"User {user_id}: {len(strava_activities)} activities processed")


def process_activity(activity, user_id, strava_client, db: Session):
    # Get the activity by Strava ID from the user
    activity = crud_activities.get_activity_by_strava_id_from_user_id(
        activity.id, user_id, db
    )

    # Check if activity is None
    if activity:
        # Log an informational event if the activity already exists
        logger.info(
            f"User {user_id}: Activity {activity.id} already exists. Will skip processing"
        )
        # Return None
        return None

    # Parse start and end dates
    start_date_parsed = activity.start_date

    # Ensure activity.elapsed_time is a numerical value
    elapsed_time_seconds = (
        activity.elapsed_time.total_seconds()
        if isinstance(activity.elapsed_time, timedelta)
        else activity.elapsed_time
    )

    end_date_parsed = start_date_parsed + timedelta(seconds=elapsed_time_seconds)

    # Initialize location variables
    latitude, longitude = None, None

    if hasattr(activity, "start_latlng") and activity.start_latlng is not None:
        latitude = activity.start_latlng.lat
        longitude = activity.start_latlng.lon

    # Initialize location variables
    city = activity.location_city
    town = activity.location_state
    country = activity.location_country

    # List to store constructed waypoints
    waypoints = []

    # Initialize variables for elevation gain and loss
    elevation_gain = 0
    elevation_loss = 0
    previous_elevation = None

    # Get streams for the activity
    streams = strava_client.get_activity_streams(
        activity.id,
        types=[
            "latlng",
            "altitude",
            "time",
            "heartrate",
            "cadence",
            "watts",
            "velocity_smooth",
        ],
    )

    # Extract data from streams
    lat_lon = streams["latlng"].data if "latlng" in streams else []
    lat_lon_waypoints = []
    ele = streams["altitude"].data if "altitude" in streams else []
    ele_waypoints = []
    is_elevation_set = False
    time = streams["time"].data if "time" in streams else []
    hr = streams["heartrate"].data if "heartrate" in streams else []
    hr_waypoints = []
    is_heart_rate_set = False
    cad = streams["cadence"].data if "cadence" in streams else []
    cad_waypoints = []
    is_cadence_set = False
    power = streams["watts"].data if "watts" in streams else []
    power_waypoints = []
    is_power_set = False
    vel = streams["velocity_smooth"].data if "velocity_smooth" in streams else []
    vel_waypoints = []
    is_velocity_set = False
    pace_waypoints = []

    for i in range(len(lat_lon)):
        lat_lon_waypoints.append(
            {
                "time": time[i],
                "lat": lat_lon[i][0],
                "lon": lat_lon[i][1],
            }
        )

    for i in range(len(ele)):
        # Calculate elevation gain and loss on-the-fly
        current_elevation = ele[i] if i < len(ele) else None

        if current_elevation is not None:
            if previous_elevation is not None:
                elevation_change = current_elevation - previous_elevation

                if elevation_change > 0:
                    elevation_gain += elevation_change
                else:
                    elevation_loss += abs(elevation_change)

            previous_elevation = current_elevation

        ele_waypoints.append({"time": time[i], "ele": ele[i]})
        is_elevation_set = True

    for i in range(len(hr)):
        hr_waypoints.append({"time": time[i], "hr": hr[i]})
        is_heart_rate_set = True

    for i in range(len(cad)):
        cad_waypoints.append({"time": time[i], "cad": cad[i]})
        is_cadence_set = True

    for i in range(len(power)):
        power_waypoints.append({"time": time[i], "power": power[i]})
        is_power_set = True

    for i in range(len(vel)):
        vel_waypoints.append({"time": time[i], "vel": vel[i]})
        pace_calculation = 1 / vel[i]
        pace_waypoints.append({"time": time[i], "pace": pace_calculation})
        is_velocity_set = True

    # Calculate average speed, pace, and watts
    average_speed = 0
    if activity.average_speed is not None:
        average_speed = (
            float(activity.average_speed.magnitude)
            if isinstance(activity.average_speed, Quantity)
            else activity.average_speed
        )

    average_pace = 1 / average_speed if average_speed != 0 else 0

    average_watts = 0
    if activity.average_watts is not None:
        average_watts = activity.average_watts

    # Create the activity in the database
    created_activity = crud_activities.create_activity(
        schema_activities.Activity(
            user_id=user_id,
            name=activity.name,
            distance=(
                round(float(activity.distance))
                if isinstance(activity.distance, Quantity)
                else round(activity.distance)
            ),
            activity_type=activity_processor.define_activity_type(activity.sport_type),
            start_time=start_date_parsed,
            end_time=end_date_parsed,
            city=city,
            town=town,
            country=country,
            waypoints=waypoints,
            elevation_gain=elevation_gain,
            elevation_loss=elevation_loss,
            pace=average_pace,
            average_speed=average_speed,
            average_power=average_watts,
            calories=activity.calories,
            strava_gear_id=activity.gear_id,
            strava_activity_id=activity.id,
        ),
        db,
    )

    activity_streams = []

    # List of conditions, stream types, and corresponding waypoints
    stream_data = [
        (is_heart_rate_set, 1, hr_waypoints),
        (is_power_set, 2, power_waypoints),
        (is_cadence_set, 3, cad_waypoints),
        (is_elevation_set, 4, ele_waypoints),
        (is_velocity_set, 5, vel_waypoints),
        (is_velocity_set, 6, pace_waypoints),
        (latitude is not None and longitude is not None, 7, lat_lon_waypoints),
    ]

    for condition, stream_type, waypoints in stream_data:
        if condition:
            activity_streams.append(
                schema_activity_streams.ActivityStreams(
                    activity_id=created_activity.id,
                    stream_type=stream_type,
                    stream_waypoints=waypoints,
                    strava_activity_stream_id=None,
                )
            )

    crud_activity_streams.create_activity_streams(activity_streams, db)

    """ activity_streams = []

    if is_heart_rate_set:
        activity_streams.append(
            schema_activity_streams.ActivityStreams(
                activity_id=created_activity.id,
                stream_type=1,
                stream_waypoints=hr_waypoints,
                strava_activity_stream_id=None,
            )
        )
    
    if is_power_set:
        activity_streams.append(
            schema_activity_streams.ActivityStreams(
                activity_id=created_activity.id,
                stream_type=2,
                stream_waypoints=power_waypoints,
                strava_activity_stream_id=None,
            )
        )

    if is_cadence_set:
        activity_streams.append(
            schema_activity_streams.ActivityStreams(
                activity_id=created_activity.id,
                stream_type=3,
                stream_waypoints=cad_waypoints,
                strava_activity_stream_id=None,
            )
        )

    if is_elevation_set:
        activity_streams.append(
            schema_activity_streams.ActivityStreams(
                activity_id=created_activity.id,
                stream_type=4,
                stream_waypoints=ele_waypoints,
                strava_activity_stream_id=None,
            )
        )

    if is_velocity_set:
        activity_streams.append(
            schema_activity_streams.ActivityStreams(
                activity_id=created_activity.id,
                stream_type=5,
                stream_waypoints=vel_waypoints,
                strava_activity_stream_id=None,
            )
        )

    if is_velocity_set:
        activity_streams.append(
            schema_activity_streams.ActivityStreams(
                activity_id=created_activity.id,
                stream_type=6,
                stream_waypoints=pace_waypoints,
                strava_activity_stream_id=None,
            )
        )

    if latitude is not None and longitude is not None:
        activity_streams.append(
            schema_activity_streams.ActivityStreams(
                activity_id=created_activity.id,
                stream_type=7,
                stream_waypoints=lat_lon_waypoints,
                strava_activity_stream_id=None,
            )
        ) """
    
