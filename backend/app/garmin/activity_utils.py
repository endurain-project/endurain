import os
import zipfile

from datetime import datetime, timedelta, date
import garminconnect
from sqlalchemy.orm import Session

import garmin.utils as garmin_utils
import garmin.logger as garmin_logger

import activities.utils as activities_utils
import activities.crud as activities_crud

import users.crud as users_crud

from core.database import SessionLocal


def fetch_and_process_activities(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    user_id: int,
    db: Session,
) -> int:
    # Fetch Garmin Connect activities after the specified start date
    garmin_activities = garminconnect_client.get_activities_by_date(
        start_date, date.today()
    )

    if garmin_activities is None:
        # Log an informational event if no activities were found
        garmin_logger.print_to_log_and_console(
            f"User {user_id}: No new Garmin Connect activities found after {start_date}: garmin_activities is None"
        )

        # Return 0 to indicate no activities were processed
        return 0

    # Download activities
    for activity in garmin_activities:
        # Get the activity ID
        activity_id = activity["activityId"]

        # Check if the activity is already stored in the database
        activity_db = activities_crud.get_activity_by_garminconnect_id_from_user_id(
            activity_id, user_id, db
        )

        if activity_db:
            # Log an informational event if the activity is already stored
            garmin_logger.print_to_log(
                f"User {user_id}: Activity {activity_id} already stored in the database"
            )
            continue

        garmin_logger.print_to_log(
            f"User {user_id}: Processing activity {activity_id}"
        )

        # Get activity gear
        activity_gear = garminconnect_client.get_activity_gear(activity_id)

        # Download the activity in original format (.zip file)
        zip_data = garminconnect_client.download_activity(
            activity_id, dl_fmt=garminconnect_client.ActivityDownloadFormat.ORIGINAL
        )
        # Save the zip file
        output_file = f"files/{str(activity_id)}.zip"

        # Write the ZIP data to the output file
        with open(output_file, "wb") as fb:
            fb.write(zip_data)

        # Array to store the names of extracted files
        extracted_files = []

        # Open the ZIP file
        with zipfile.ZipFile(output_file, "r") as zip_ref:
            # Extract all contents to the specified directory
            zip_ref.extractall("files")
            # Populate the array with file names
            extracted_files = zip_ref.namelist()

        os.remove(output_file)

        for file in extracted_files:
            activities_utils.parse_and_store_activity_from_file(
                user_id, f"files/{file}", db, True, activity_gear
            )

    # Return the number of activities processed
    return len(garmin_activities)


def retrieve_garminconnect_users_activities_for_days(days: int):
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
        get_user_garminconnect_activities_by_days(
            (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
            user.id,
        )


def get_user_garminconnect_activities_by_days(start_date: datetime, user_id: int):
    # Create a new database session
    db = SessionLocal()

    try:
        # Get the user integrations by user ID
        user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(
            user_id, db
        )

        if user_integrations is None:
            garmin_logger.print_to_log(f"User {user_id}: Garmin Connect not linked")
            return None

        # Log the start of the activities processing
        garmin_logger.print_to_log(
            f"User {user_id}: Started Garmin Connect activities processing"
        )

        # Create a Garmin Connect client with the user's access token
        garminconnect_client = garmin_utils.login_garminconnect_using_tokens(
            user_integrations.garminconnect_oauth1,
            user_integrations.garminconnect_oauth2,
        )

        # Fetch Garmin Connect activities after the specified start date
        num_garminconnect_activities_processed = fetch_and_process_activities(
            garminconnect_client, start_date, user_id, db
        )

        # Log an informational event for tracing
        garmin_logger.print_to_log(
            f"User {user_id}: {num_garminconnect_activities_processed} Garmin Connect activities processed"
        )
    finally:
        # Ensure the session is closed after use
        db.close()
