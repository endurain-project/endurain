from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client

import core.logger as core_logger

import strava.utils as strava_utils
import strava.athlete_utils as strava_athlete_utils

import gears.gear.schema as gears_schema
import gears.gear.crud as gears_crud

import activities.activity.schema as activities_schema
import activities.activity.crud as activities_crud

import users.user_integrations.crud as user_integrations_crud

from core.database import SessionLocal


def get_strava_gear(gear_id: str, strava_client: Client):
    # Fetch Strava gear
    try:
        strava_gear = strava_client.get_gear(gear_id)
    except Exception as err:
        # Log an error event if the gear could not be fetched
        core_logger.print_to_log(
            f"Error fetching Strava gear with ID: {err}. Returning 424 Failed Dependency",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Not able to fetch Strava gear",
        )

    if strava_gear is None:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Not able to fetch Strava gear",
        )

    return strava_gear


def fetch_and_process_gear(strava_client: Client, user_id: int, db: Session) -> int:
    # Fetch Strava athlete
    try:
        strava_athlete = strava_athlete_utils.get_strava_athlete(strava_client)
    except Exception as err:
        raise err

    # Initialize an empty list for results
    strava_gear = []

    # Store the athlete's bikes
    athlete_bikes = strava_athlete.bikes
    athlete_shoes = strava_athlete.shoes

    for bike in athlete_bikes:
        strava_gear.append(process_gear(bike, "bike", user_id, strava_client, db))

    for shoe in athlete_shoes:
        strava_gear.append(process_gear(shoe, "shoe", user_id, strava_client, db))

    if strava_gear is None:
        # Log an informational event if no gear were found
        core_logger.print_to_log(
            f"User {user_id}: No new Strava gear found: strava_gear is None"
        )

        # Return 0 to indicate no gear were processed
        return 0

    # Save the gear to the database
    gears_crud.create_multiple_gears(strava_gear, user_id, db)

    # Return the number of activities processed
    return len(strava_gear)


def process_gear(
    gear, type: str, user_id: int, strava_client: Client, db: Session
) -> gears_schema.Gear | None:
    # Get the gear by strava id from user id
    gear_db = gears_crud.get_gear_by_strava_id_from_user_id(gear.id, user_id, db)

    # Skip existing gear
    if gear_db:
        return None

    # Get the gear from Strava
    try:
        strava_gear = get_strava_gear(gear.id, strava_client)
    except Exception as err:
        raise err

    new_gear = gears_schema.Gear(
        brand=strava_gear.brand_name,
        model=strava_gear.model_name,
        nickname=strava_gear.name,
        gear_type=1 if type == "bike" else 2,
        user_id=user_id,
        is_active=1,
        strava_gear_id=gear.id,
    )

    return new_gear


def iterate_over_activities_and_set_gear(
    activity: activities_schema.Activity,
    gears: list[gears_schema.Gear],
    counter: int,
    user_id: int,
    db: Session,
) -> dict:

    # Iterate over gears and set gear if applicable
    if activity.strava_gear_id is not None:
        for gear in gears:
            if activity.strava_gear_id == gear.strava_gear_id:
                activity.gear_id = gear.id
                counter += 1
                break

    # Return the counter
    return {"counter": counter, "activity": activity}


def set_activities_gear(user_id: int, db: Session) -> int:
    # Get user activities
    activities = activities_crud.get_user_activities(user_id, db)

    # Skip if no activities
    if activities is None:
        return 0

    # Get user gears
    gears = gears_crud.get_gear_user(user_id, db)

    # Skip if no gears
    if gears is None:
        return 0

    # Initialize a counter
    counter = 0

    # Initialize an empty list for results
    activities_parsed = []

    # iterate over activities and set gear if applicable
    for activity in activities:
        parsed_activity = iterate_over_activities_and_set_gear(
            activity, gears, counter, user_id, db
        )
        counter = parsed_activity["counter"]
        activities_parsed.append(parsed_activity["activity"])

    activities_crud.edit_multiple_activities_gear_id(activities_parsed, user_id, db)

    return counter


def get_user_gear(user_id: int):
    # Create a new database session
    db = SessionLocal()

    try:
        # Get the user integrations by user ID
        user_integrations = strava_utils.fetch_user_integrations_and_validate_token(
            user_id, db
        )

        # Log the start of the activities processing
        core_logger.print_to_log(f"User {user_id}: Started Strava gear processing")

        # Create a Strava client with the user's access token
        strava_client = strava_utils.create_strava_client(user_integrations)

        # Set the user's gear to sync to True
        user_integrations_crud.set_user_strava_sync_gear(user_id, True, db)

        # Fetch Strava gear
        num_strava_gear_processed = fetch_and_process_gear(strava_client, user_id, db)

        # Log an informational event for tracing
        core_logger.print_to_log(
            f"User {user_id}: {num_strava_gear_processed} Strava gear processed"
        )

        # Log an informational event for tracing
        core_logger.print_to_log(
            f"User {user_id}: Will parse current activities and set gear if applicable"
        )

        num_gear_activities_set = set_activities_gear(user_id, db)

        # Log an informational event for tracing
        core_logger.print_to_log(
            f"User {user_id}: {num_gear_activities_set} activities where gear was set"
        )
    finally:
        db.close()
