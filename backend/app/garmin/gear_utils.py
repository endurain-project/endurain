import garminconnect
from sqlalchemy.orm import Session

import core.logger as core_logger

import garmin.utils as garmin_utils

import gears.gear.schema as gears_schema
import gears.gear.crud as gears_crud

import activities.activity.schema as activities_schema
import activities.activity.crud as activities_crud

import users.users_integrations.crud as user_integrations_crud

from core.database import SessionLocal


def fetch_and_process_gear(
    garminconnect_client: garminconnect.Garmin, user_id: int, db: Session
) -> int:
    # Fetch Garmin athlete
    last_used_device = garminconnect_client.get_device_last_used()

    # Get the user gear
    gears = garminconnect_client.get_gear(last_used_device["userProfileNumber"])

    # Initialize an empty list for results
    processed_gears = []

    for gear in gears:
        processed_gears.append(process_gear(gear, user_id, db))

    if processed_gears is None:
        # Log an informational event if no gear were found
        core_logger.print_to_log(
            f"User {user_id}: No new Garmin Connect gear found: garminconnect_gear is None"
        )

        # Return 0 to indicate no gear were processed
        return 0

    # Save the gear to the database
    gears_crud.create_multiple_gears(processed_gears, user_id, db)

    # Return the number of activities processed
    return len(processed_gears)


def process_gear(gear, user_id: int, db: Session) -> gears_schema.Gear | None:
    # Get the gear by garminconnect uuid from user id
    gear_db = gears_crud.get_gear_by_garminconnect_id_from_user_id(
        gear["uuid"], user_id, db
    )

    # Skip existing gear
    if gear_db:
        return None

    new_gear = gears_schema.Gear(
        brand=gear["gearMakeName"] if gear["gearMakeName"] else None,
        model=gear["gearModelName"] if gear["gearModelName"] else None,
        nickname=(
            gear["displayName"] if gear["displayName"] else gear["customMakeModel"]
        ),
        gear_type=1 if gear["gearTypeName"] == "Bike" else 2,
        user_id=user_id,
        active=True if gear["gearStatusName"] == "active" else False,
        garminconnect_gear_id=gear["uuid"],
    )

    return new_gear


def iterate_over_activities_and_set_gear(
    activity: activities_schema.Activity,
    gears: list[gears_schema.Gear],
    counter: int,
) -> dict:

    # Iterate over gears and set gear if applicable
    if activity.garminconnect_gear_id is not None:
        for gear in gears:
            if activity.garminconnect_gear_id == gear.garminconnect_gear_id:
                core_logger.print_to_log(f"Gear found: {gear.nickname}")
                activity.gear_id = gear.id
                counter += 1
                break

    # Return the counter
    return {"counter": counter, "activity": activity}


def set_activities_gear(user_id: int, db: Session) -> int:
    # Get user activities
    activities = (
        activities_crud.get_user_activities_by_user_id_and_garminconnect_gear_set(
            user_id, db
        )
    )

    # Skip if no activities
    if activities is None:
        core_logger.print_to_log(f"User {user_id}: 0 activities found")
        return 0

    core_logger.print_to_log(f"User {user_id}: {len(activities)} activities found")

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
        parsed_activity = iterate_over_activities_and_set_gear(activity, gears, counter)
        counter = parsed_activity["counter"]
        activities_parsed.append(parsed_activity["activity"])

    if len(activities_parsed) > 0:
        activities_crud.edit_multiple_activities_gear_id(activities_parsed, user_id, db)

    return counter


def get_user_gear(user_id: int):
    # Create a new database session using context manager
    with SessionLocal() as db:
        # Log the start of the activities processing
        core_logger.print_to_log(
            f"User {user_id}: Started Garmin Connect gear processing"
        )

        # Get the user integrations by user ID
        user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(
            user_id, db
        )

        if user_integrations is None:
            core_logger.print_to_log(f"User {user_id}: Garmin Connect not linked")
            return None

        # Create a Garmin Connect client with the user's access token
        garminconnect_client = garmin_utils.login_garminconnect_using_tokens(
            user_integrations.garminconnect_oauth1,
            user_integrations.garminconnect_oauth2,
        )

        # Set the user's gear to sync to True
        user_integrations_crud.set_user_garminconnect_sync_gear(user_id, True, db)

        # Fetch Garmin Connect gear
        num_garmiconnect_gear_processed = fetch_and_process_gear(
            garminconnect_client, user_id, db
        )

        # Log an informational event for tracing
        core_logger.print_to_log(
            f"User {user_id}: {num_garmiconnect_gear_processed} Garmin Connect gear processed"
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
