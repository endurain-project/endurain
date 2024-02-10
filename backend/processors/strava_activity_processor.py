import logging

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from stravalib.client import Client
from pint import Quantity

from schemas import schema_activities, schema_activity_streams, schema_user_integrations
from crud import (
    crud_activities,
    crud_activity_streams,
    crud_users,
    crud_gear,
)
from database import SessionLocal
from processors import activity_processor, strava_processor

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def fetch_and_process_activities(
    strava_client: Client,
    start_date: datetime,
    user_id: int,
    user_integrations: schema_user_integrations.UserIntegrations,
    db: Session,
) -> int:
    # Fetch Strava activities after the specified start date
    strava_activities = list(strava_client.get_activities(after=start_date))

    if strava_activities is None:
        # Log an informational event if no activities were found
        logger.info(
            f"User {user_id}: No new Strava activities found after {start_date}: strava_activities is None"
        )

        # Return 0 to indicate no activities were processed
        return 0

    # Process the activities
    for activity in strava_activities:
        process_activity(activity, user_id, strava_client, user_integrations, db)

    # Return the number of activities processed
    return len(strava_activities)


def parse_activity(activity, user_id: int, strava_client: Client, user_integrations: schema_user_integrations.UserIntegrations, db: Session) -> dict:
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
    city, town, country = None, None, None

    parsed_location = activity_processor.location_based_on_coordinates(
        latitude, longitude
    )

    if parsed_location is not None:
        if "city" in parsed_location:
            city = parsed_location["city"]
        if "town" in parsed_location:
            town = parsed_location["town"]
        if "country" in parsed_location:
            country = parsed_location["country"]

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

    gear_id = None

    if user_integrations.strava_sync_gear:
        # set the gear id for the activity
        gear = crud_gear.get_gear_by_strava_id_from_user_id(activity.gear_id, user_id, db)

        # set the gear id for the activity
        if gear is not None:
            gear_id = gear.id

    # Create the activity object
    activity_to_store = schema_activities.Activity(
        user_id=user_id,
        name=activity.name,
        distance=(
            round(float(activity.distance))
            if isinstance(activity.distance, Quantity)
            else round(activity.distance)
        ),
        description=activity.description,
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
        gear_id=gear_id,
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


def process_activity(
    activity,
    user_id: int,
    strava_client: Client,
    user_integrations: schema_user_integrations.UserIntegrations,
    db: Session,
):
    # Get the activity by Strava ID from the user
    activity_db = strava_processor.fetch_and_validate_activity(activity.id, user_id, db)

    # Check if activity is None and return None if it is
    if activity_db is not None:
        return None

    # Log an informational event for activity processing
    logger.info(f"User {user_id}: Strava activity {activity.id} will be processed")

    # Parse the activity and streams
    parsed_activity = parse_activity(activity, user_id, strava_client, user_integrations, db)

    # Save the activity and streams to the database
    save_activity_and_streams(
        parsed_activity["activity_to_store"], parsed_activity["stream_data"], db
    )


def retrieve_strava_users_activities_for_days(days: int):
    # Create a new database session
    db = SessionLocal()

    try:
        # Get all users
        users = crud_users.get_all_users(db)
    finally:
        # Ensure the session is closed after use
        db.close()

    # Process the activities for each user
    for user in users:
        get_user_strava_activities_by_days(
            (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
            user.id,
        )


def get_user_strava_activities_by_days(start_date: datetime, user_id: int):
    # Create a new database session
    db = SessionLocal()

    try:
        # Get the user integrations by user ID
        user_integrations = strava_processor.fetch_user_integrations_and_validate_token(
            user_id, db
        )

        # Log the start of the activities processing
        logger.info(f"User {user_id}: Started Strava activities processing")

        # Create a Strava client with the user's access token
        strava_client = strava_processor.create_strava_client(user_integrations)

        # Fetch Strava activities after the specified start date
        num_strava_activities_processed = fetch_and_process_activities(
            strava_client, start_date, user_id, user_integrations, db
        )

        # Log an informational event for tracing
        logger.info(
            f"User {user_id}: {num_strava_activities_processed} Strava activities processed"
        )
    finally:
        # Ensure the session is closed after use
        db.close()
