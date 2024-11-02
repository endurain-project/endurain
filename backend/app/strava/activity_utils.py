import logging

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from stravalib.client import Client

import activities.schema as activities_schema
import activities.crud as activities_crud
import activities.utils as activities_utils

import activity_streams.schema as activity_streams_schema
import activity_streams.crud as activity_streams_crud

import user_integrations.schema as user_integrations_schema

import users.crud as users_crud

import gears.crud as gears_crud

import strava.utils as strava_utils

from database import SessionLocal

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def fetch_and_process_activities(
    strava_client: Client,
    start_date: datetime,
    user_id: int,
    user_integrations: user_integrations_schema.UserIntegrations,
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


def parse_activity(
    activity,
    user_id: int,
    strava_client: Client,
    user_integrations: user_integrations_schema.UserIntegrations,
    db: Session,
) -> dict:
    # Get the detailed activity
    detailedActivity = strava_client.get_activity(activity.id)

    # Parse start and end dates
    start_date_parsed = detailedActivity.start_date

    # Ensure activity.elapsed_time is a numerical value
    total_elapsed_time = (
        detailedActivity.elapsed_time.total_seconds()
        if isinstance(detailedActivity.elapsed_time, timedelta)
        else detailedActivity.elapsed_time
    )

    total_timer_time = (
        detailedActivity.moving_time.total_seconds()
        if isinstance(detailedActivity.moving_time, timedelta)
        else detailedActivity.moving_time
    )

    end_date_parsed = start_date_parsed + timedelta(seconds=total_elapsed_time)

    # Initialize location variables
    city, town, country = None, None, None
    if detailedActivity.location_city is not None:
        city = detailedActivity.location_city
    if detailedActivity.location_state is not None:
        town = detailedActivity.location_state
    if detailedActivity.location_country is not None:
        country = detailedActivity.location_country

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

    ele_gain, ele_loss = None, None
    # Calculate elevation gain and loss
    if ele_waypoints:
        ele_gain, ele_loss = activities_utils.calculate_elevation_gain_loss(
            ele_waypoints
        )

        if detailedActivity.total_elevation_gain is not None:
            ele_gain = round(detailedActivity.total_elevation_gain)

    # Get average and max speed
    avg_speed = None
    if detailedActivity.average_speed is not None:
        avg_speed = detailedActivity.average_speed

    max_speed = None
    if detailedActivity.max_speed is not None:
        max_speed = detailedActivity.max_speed

    # Calculate average pace
    average_pace = 1 / avg_speed if avg_speed != 0 else None

    avg_hr, max_hr = None, None
    # Get average and max heart rate
    if detailedActivity.average_heartrate is not None:
        avg_hr = detailedActivity.average_heartrate

    if detailedActivity.max_heartrate is not None:
        max_hr = detailedActivity.max_heartrate

    avg_cadence, max_cadence = None, None
    # Calculate average and maximum cadence
    if cad_waypoints:
        avg_cadence, max_cadence = activities_utils.calculate_avg_and_max(
            cad_waypoints, "cad"
        )

        if detailedActivity.average_cadence is not None:
            avg_cadence = detailedActivity.average_cadence

    # Get average and max power
    avg_power = None
    if detailedActivity.average_watts is not None:
        avg_power = detailedActivity.average_watts

    max_power = None
    if detailedActivity.max_watts is not None:
        max_power = detailedActivity.max_watts

    # Calculate normalized power
    np = None
    if power_waypoints:
        np = activities_utils.calculate_np(power_waypoints)

    # List of conditions, stream types, and corresponding waypoints
    stream_data = [
        (is_heart_rate_set, 1, hr_waypoints),
        (is_power_set, 2, power_waypoints),
        (is_cadence_set, 3, cad_waypoints),
        (is_elevation_set, 4, ele_waypoints),
        (is_velocity_set, 5, vel_waypoints),
        (is_velocity_set, 6, pace_waypoints),
        (detailedActivity.start_latlng is not None, 7, lat_lon_waypoints),
    ]

    gear_id = None

    if user_integrations.strava_sync_gear:
        # set the gear id for the activity
        gear = gears_crud.get_gear_by_strava_id_from_user_id(
            detailedActivity.gear_id, user_id, db
        )

        # set the gear id for the activity
        if gear is not None:
            gear_id = gear.id

    # Create the activity object
    activity_to_store = activities_schema.Activity(
        user_id=user_id,
        name=detailedActivity.name,
        distance=round(detailedActivity.distance),
        description=detailedActivity.description,
        activity_type=activities_utils.define_activity_type(detailedActivity.sport_type),
        start_time=start_date_parsed.strftime("%Y-%m-%dT%H:%M:%S"),
        end_time=end_date_parsed.strftime("%Y-%m-%dT%H:%M:%S"),
        total_elapsed_time=total_elapsed_time,
        total_timer_time=total_timer_time,
        city=city,
        town=town,
        country=country,
        elevation_gain=ele_gain,
        elevation_loss=ele_loss,
        pace=average_pace,
        average_speed=avg_speed,
        max_speed=max_speed,
        average_power=avg_power,
        max_power=max_power,
        normalized_power=np,
        average_hr=avg_hr,
        max_hr=max_hr,
        average_cad=avg_cadence,
        max_cad=max_cadence,
        calories=round(detailedActivity.calories),
        gear_id=gear_id,
        strava_gear_id=detailedActivity.gear_id,
        strava_activity_id=int(activity.id),
    )

    # Return the activity and stream data
    return {"activity_to_store": activity_to_store, "stream_data": stream_data}


def save_activity_and_streams(
    activity: activities_schema.Activity, stream_data: list, db: Session
):
    # Create the activity and get the ID
    created_activity = activities_crud.create_activity(activity, db)

    # Create the empty array of activity streams
    activity_streams = []

    # Create the activity streams objects
    for is_set, stream_type, waypoints in stream_data:
        if is_set:
            activity_streams.append(
                activity_streams_schema.ActivityStreams(
                    activity_id=created_activity.id,
                    stream_type=stream_type,
                    stream_waypoints=waypoints,
                    strava_activity_stream_id=None,
                )
            )

    # Create the activity streams in the database
    activity_streams_crud.create_activity_streams(activity_streams, db)


def process_activity(
    activity,
    user_id: int,
    strava_client: Client,
    user_integrations: user_integrations_schema.UserIntegrations,
    db: Session,
):
    # Get the activity by Strava ID from the user
    activity_db = strava_utils.fetch_and_validate_activity(activity.id, user_id, db)

    # Check if activity is None and return None if it is
    if activity_db is not None:
        return None

    # Log an informational event for activity processing
    logger.info(f"User {user_id}: Strava activity {activity.id} will be processed")

    # Parse the activity and streams
    parsed_activity = parse_activity(
        activity, user_id, strava_client, user_integrations, db
    )

    # Save the activity and streams to the database
    save_activity_and_streams(
        parsed_activity["activity_to_store"], parsed_activity["stream_data"], db
    )


def retrieve_strava_users_activities_for_days(days: int):
    # Create a new database session
    db = SessionLocal()

    try:
        # Get all users
        users = users_crud.get_all_users(db)
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
        user_integrations = strava_utils.fetch_user_integrations_and_validate_token(
            user_id, db
        )

        if user_integrations is None:
            logger.info(f"User {user_id}: Strava not linked")
            return None

        # Log the start of the activities processing
        logger.info(f"User {user_id}: Started Strava activities processing")

        # Create a Strava client with the user's access token
        strava_client = strava_utils.create_strava_client(user_integrations)

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
