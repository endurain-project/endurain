import logging
import os
import requests

from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client
from pint import Quantity

from schemas import schema_activities, schema_activity_streams, schema_user_integrations
from crud import crud_user_integrations, crud_activities, crud_activity_streams, crud_users
from dependencies import dependencies_database
from processors import activity_processor

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def refresh_strava_token(db: Session):
    # Get all users
    users = crud_users.get_all_users(db)

    # Iterate through all users
    for user in users:
        # Get the user integrations by user ID
        user_integrations = crud_user_integrations.get_user_integrations_by_user_id(user.id, db)

        # Check if user_integrations strava token is not None
        if user_integrations.strava_token is not None:
            refresh_time = user_integrations.strava_token_expires_at - timedelta(
                minutes=60
            )

            if datetime.utcnow() > refresh_time:
                # Strava token refresh endpoint
                token_url = "https://www.strava.com/oauth/token"
                # Parameters for the token refresh request
                payload = {
                    "client_id": os.environ.get("STRAVA_CLIENT_ID"),
                    "client_secret": os.environ.get("STRAVA_CLIENT_SECRET"),
                    "refresh_token": user_integrations.strava_refresh_token,
                    "grant_type": "refresh_token",
                }

                try:
                    # Send a POST request to the token URL
                    response = requests.post(token_url, data=payload)

                    # Check if the response status code is not 200
                    if response.status_code != 200:
                        # Raise an HTTPException with a 424 Failed Dependency status code
                        logger.error("Unable to retrieve tokens for refresh process from Strava")

                    tokens = response.json()
                except Exception as err:
                    # Log the exception
                    logger.error(f"Error in refresh_strava_token: {err}", exc_info=True)

                    # Raise an HTTPException with a 500 Internal Server Error status code
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Internal Server Error",
                    ) from err
                finally:
                    # Update the user integrations with the tokens
                    crud_user_integrations.link_strava_account(user_integrations, tokens, db)
        #else:
            # Log an informational event if the Strava access token is not found
            #logger.info(f"User {user.id}: Strava access token not found")


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> schema_user_integrations.UserIntegrations:
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

    # Return the user integrations
    return user_integrations


def create_strava_client(
    user_integrations: schema_user_integrations.UserIntegrations,
) -> Client:
    # Create a Strava client with the user's access token and return it
    return Client(access_token=user_integrations.strava_token)


def fetch_and_process_activities(
    strava_client: Client, start_date: datetime, user_id: int, db: Session
) -> int:
    # Fetch Strava activities after the specified start date
    strava_activities = list(strava_client.get_activities(after=start_date))

    if strava_activities is None:
        # Log an informational event if no activities were found
        logger.info(
            f"User {user_id}: No new activities found after {start_date}: strava_activities is None"
        )

        # Return 0 to indicate no activities were processed
        return 0

    # Process the activities
    for activity in strava_activities:
        process_activity(activity, user_id, strava_client, db)

    # Return the number of activities processed
    return len(strava_activities)


def fetch_and_validate_activity(
    activity_id: int, user_id: int, db: Session
) -> schema_activities.Activity | None:
    # Get the activity by Strava ID from the user
    activity_db = crud_activities.get_activity_by_strava_id_from_user_id(
        activity_id, user_id, db
    )

    # Check if activity is None
    if activity_db:
        # Log an informational event if the activity already exists
        logger.info(
            f"User {user_id}: Activity {activity_id} already exists. Will skip processing"
        )
        
        # Return None
        return activity_db
    else:
        return None


def parse_activity(activity, user_id: int, strava_client: Client) -> dict:
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
        # Append velocity to the velocity waypoints
        vel_waypoints.append({"time": time[i], "vel": vel[i]})

        # Calculate pace on-the-fly. If velocity is 0, pace is 0
        pace_calculation = 0
        if vel[i] != 0:
            pace_calculation = 1 / vel[i]

        # Append pace to the pace waypoints
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

    # Create the activity object
    activity_to_store = schema_activities.Activity(
        user_id=user_id,
        name=activity.name,
        distance=(
            round(float(activity.distance))
            if isinstance(activity.distance, Quantity)
            else round(activity.distance)
        ),
        activity_type=activity_processor.define_activity_type(activity.sport_type),
        start_time=start_date_parsed.strftime("%Y-%m-%dT%H:%M:%S"),
        end_time=end_date_parsed.strftime("%Y-%m-%dT%H:%M:%S"),
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
        strava_activity_id=int(activity.id),
    )

    # Return the activity and stream data
    return {"activity_to_store": activity_to_store, "stream_data": stream_data}


def save_activity_and_streams(
    activity: schema_activities.Activity, stream_data: list, db: Session
):
    # Create the activity and get the ID
    created_activity = crud_activities.create_activity(activity, db)

    # Create the empty array of activity streams
    activity_streams = []

    # Create the activity streams objects
    for is_set, stream_type, waypoints in stream_data:
        if is_set:
            activity_streams.append(
                schema_activity_streams.ActivityStreams(
                    activity_id=created_activity.id,
                    stream_type=stream_type,
                    stream_waypoints=waypoints,
                    strava_activity_stream_id=None,
                )
            )

    # Create the activity streams in the database
    crud_activity_streams.create_activity_streams(activity_streams, db)


def process_activity(activity, user_id: int, strava_client: Client, db: Session):
    # Get the activity by Strava ID from the user
    activity_db = fetch_and_validate_activity(activity.id, user_id, db)

    # Check if activity is None and return None if it is
    if activity_db is not None:
        return None

    # Log an informational event for activity processing
    logger.info(f"User {user_id}: Activity {activity.id} will be processed")

    # Parse the activity and streams
    parsed_activity = parse_activity(activity, user_id, strava_client)

    # Save the activity and streams to the database
    save_activity_and_streams(
        parsed_activity["activity_to_store"], parsed_activity["stream_data"], db
    )


def get_user_strava_activities_by_days(start_date: datetime, user_id: int):
    # Get the first (and only) item from the generator
    db = next(dependencies_database.get_db())

    try:
        # Get the user integrations by user ID
        user_integrations = fetch_user_integrations_and_validate_token(user_id, db)

        # Log the start of the activities processing
        logger.info(f"User {user_id}: Started activities processing")

        # Create a Strava client with the user's access token
        strava_client = create_strava_client(user_integrations)

        # Fetch Strava activities after the specified start date
        num_strava_activities_processed = fetch_and_process_activities(
            strava_client, start_date, user_id, db
        )

        # Log an informational event for tracing
        logger.info(
            f"User {user_id}: {num_strava_activities_processed} activities processed"
        )
    finally:
        # Ensure the session is closed after use
        db.close()
