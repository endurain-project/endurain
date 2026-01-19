import os
import zipfile

from datetime import datetime, timedelta, timezone
import garminconnect
from sqlalchemy.orm import Session

import core.logger as core_logger
import core.config as core_config

import garmin.utils as garmin_utils

import activities.activity.schema as activities_schema
import activities.activity.utils as activities_utils
import activities.activity.crud as activities_crud

import users.users.crud as users_crud

import websocket.manager as websocket_manager

from core.database import SessionLocal


async def fetch_and_process_activities_by_dates(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    ws_manager: websocket_manager.WebSocketManager,
    db: Session,
) -> list[activities_schema.Activity] | None:
    try:
        # Fetch Garmin Connect activities for the specified date range
        garmin_activities = garminconnect_client.get_activities_by_date(
            str(start_date.date()), str(end_date.date())
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error fetching activities for user {user_id} between {start_date.date()} and {end_date.date()}: {err}",
            "error",
            exc=err,
        )
        return None

    if garmin_activities is None:
        # Log an informational event if no activities were found
        core_logger.print_to_log_and_console(
            f"User {user_id}: No new Garmin Connect activities found between {start_date.date()} and {end_date.date()}: garmin_activities is None"
        )
        # Return 0 to indicate no activities were processed
        return None

    parsed_activities = []

    # Download activities
    for activity in garmin_activities:
        # Get the activity ID
        activity_id = activity["activityId"]
        activity_name = activity["activityName"]

        # Check if the activity is already stored in the database
        activity_db = activities_crud.get_activity_by_garminconnect_id_from_user_id(
            activity_id, user_id, db
        )

        if activity_db:
            # Log an informational event if the activity is already stored
            core_logger.print_to_log(
                f"User {user_id}: Activity {activity_id} already stored in the database"
            )
            continue

        core_logger.print_to_log(f"User {user_id}: Processing activity {activity_id}")

        # Get activity gear
        activity_gear = garminconnect_client.get_activity_gear(activity_id)

        # Download the activity in original format (.zip file)
        zip_data = garminconnect_client.download_activity(
            activity_id, dl_fmt=garminconnect_client.ActivityDownloadFormat.ORIGINAL
        )
        # Save the zip file
        output_file = f"{core_config.FILES_DIR}/{str(activity_id)}.zip"

        # Write the ZIP data to the output file
        with open(output_file, "wb") as fb:
            fb.write(zip_data)

        # Array to store the names of extracted files
        extracted_files = []

        # Open the ZIP file
        with zipfile.ZipFile(output_file, "r") as zip_ref:
            # Extract all contents to the specified directory
            zip_ref.extractall(core_config.FILES_DIR)
            # Populate the array with file names
            extracted_files = zip_ref.namelist()

        try:
            os.remove(output_file)
        except OSError as err:
            core_logger.print_to_log(
                f"Error removing file {output_file}: {err}", "error", exc=err
            )

        for file_path_suffix in extracted_files:
            # Parse and store the activity from the extracted file
            full_file_path = os.path.join(core_config.FILES_DIR, file_path_suffix)

            parsed_activities.extend(
                await activities_utils.parse_and_store_activity_from_file(
                    user_id,
                    full_file_path,
                    ws_manager,
                    db,
                    True,
                    activity_gear,
                    activity_name,
                )
                or []
            )

    # Return the number of activities processed
    return parsed_activities if parsed_activities else None


async def retrieve_garminconnect_users_activities_for_days(days: int):
    ws_manager = websocket_manager.get_websocket_manager()

    # Create a new database session using context manager
    with SessionLocal() as db:
        try:
            # Get all users
            users = users_crud.get_all_users(db)

            # Calculate the start date and end date
            calculated_start_date = datetime.now(timezone.utc) - timedelta(days=days)
            calculated_end_date = datetime.now(timezone.utc)

            # Iterate through all users
            for user in users:
                try:
                    await get_user_garminconnect_activities_by_dates(
                        calculated_start_date,
                        calculated_end_date,
                        user.id,
                        ws_manager,
                        db,
                    )
                except Exception as err:
                    # Log specific errors for each user
                    core_logger.print_to_log(
                        f"Error processing activities for user {user.id} in retrieve_garminconnect_users_activities_for_days: {err}",
                        "error",
                        exc=err,
                    )
        except Exception as err:
            core_logger.print_to_log(
                f"Error getting users in retrieve_garminconnect_users_activities_for_days: {err}",
                "error",
                exc=err,
            )


def get_user_garminconnect_client(user_id: int, db: Session):
    try:
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

        # return the Garmin Connect client
        return garminconnect_client
    except Exception as err:
        # Log specific errors during getting the Garmin Connect client
        core_logger.print_to_log(
            f"Error in get_user_garminconnect_client: {err}", "error", exc=err
        )

        # Return None if the client cannot be created
        return None


async def get_user_garminconnect_activities_by_dates(
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    ws_manager: websocket_manager.WebSocketManager,
    db: Session,
) -> list[activities_schema.Activity] | None:
    try:
        # Get the Garmin Connect client for the user
        garminconnect_client = get_user_garminconnect_client(user_id, db)

        if garminconnect_client is not None:
            # Fetch Garmin Connect activities for the specified date range
            garminconnect_activities_processed = (
                await fetch_and_process_activities_by_dates(
                    garminconnect_client,
                    start_date,
                    end_date,
                    user_id,
                    ws_manager,
                    db,
                )
            )

            # Log the start of the activities processing
            core_logger.print_to_log(
                f"User {user_id}: Started Garmin Connect activities processing for date range {start_date.date()} to {end_date.date()}"
            )

            # Log an informational event for tracing
            core_logger.print_to_log(
                f"User {user_id}: {len(garminconnect_activities_processed) if garminconnect_activities_processed else 0} Garmin Connect activities processed"
            )

            # Return the processed activities
            return garminconnect_activities_processed
        # If the client is None, return None
        return None
    except Exception as err:
        # Log specific errors during Garmin Connect processing
        core_logger.print_to_log(
            f"Error in get_user_garminconnect_activities_by_dates: {err}",
            "error",
            exc=err,
        )
        return None
