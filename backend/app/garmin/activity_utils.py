import os
import zipfile

from datetime import datetime, timedelta, date, timezone
import garminconnect
from sqlalchemy.orm import Session

import core.logger as core_logger

import garmin.utils as garmin_utils

import activities.activity.schema as activities_schema
import activities.activity.utils as activities_utils
import activities.activity.crud as activities_crud

import users.user.crud as users_crud

from core.database import SessionLocal

def fetch_and_process_activities_by_dates(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    db: Session,
) -> list[activities_schema.Activity] | None:
    try:
        garmin_activities = garminconnect_client.get_activities_by_date(
            start_date.date(), end_date.date()
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error fetching activities for user {user_id} between {start_date.date()} and {end_date.date()}: {err}",
            "error",
            exc=err,
        )
        return None

    if garmin_activities is None:
        core_logger.print_to_log_and_console(
            f"User {user_id}: No new Garmin Connect activities found between {start_date.date()} and {end_date.date()}: garmin_activities is None"
        )
        return None

    parsed_activities = []

    for activity in garmin_activities:
        activity_id = activity["activityId"]
        activity_db = activities_crud.get_activity_by_garminconnect_id_from_user_id(
            activity_id, user_id, db
        )

        if activity_db:
            core_logger.print_to_log(
                f"User {user_id}: Activity {activity_id} already stored in the database"
            )
            continue

        core_logger.print_to_log(f"User {user_id}: Processing activity {activity_id}")
        activity_gear = garminconnect_client.get_activity_gear(activity_id)
        zip_data = garminconnect_client.download_activity(
            activity_id, dl_fmt=garminconnect_client.ActivityDownloadFormat.ORIGINAL
        )
        output_file = f"files/{str(activity_id)}.zip"
        with open(output_file, "wb") as fb:
            fb.write(zip_data)

        extracted_files = []
        with zipfile.ZipFile(output_file, "r") as zip_ref:
            zip_ref.extractall("files")
            extracted_files = zip_ref.namelist()

        try:
            os.remove(output_file)
        except OSError as err:
            core_logger.print_to_log(
                f"Error removing file {output_file}: {err}", "error", exc=err
            )

        for file_path_suffix in extracted_files:
            full_file_path = os.path.join("files", file_path_suffix) # Ensure correct path construction
            parsed_activities.extend(
                activities_utils.parse_and_store_activity_from_file(
                    user_id, full_file_path, db, True, activity_gear # Pass full_file_path
                )
                or []
            )
    return parsed_activities if parsed_activities else None


def retrieve_garminconnect_users_activities_for_days(days: int):
    db = SessionLocal()
    try:
        users = users_crud.get_all_users(db)
        calculated_start_date = datetime.now(timezone.utc) - timedelta(days=days)
        calculated_end_date = datetime.now(timezone.utc)

        for user in users:
            try:
                get_user_garminconnect_activities_by_dates(
                    calculated_start_date,
                    calculated_end_date,
                    user.id,
                    db,
                )
            except Exception as err:
                core_logger.print_to_log(
                    f"Error processing activities for user {user.id} in retrieve_garminconnect_users_activities_for_days: {err}",
                    "error",
                    exc=err,
                )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in retrieve_garminconnect_users_activities_for_days: {err}",
            "error",
            exc=err,
        )
    finally:
        db.close()

def get_user_garminconnect_client(user_id: int, db: Session):
    try:
        user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(
            user_id, db
        )
        if user_integrations is None:
            core_logger.print_to_log(f"User {user_id}: Garmin Connect not linked")
            return None
        garminconnect_client = garmin_utils.login_garminconnect_using_tokens(
            user_integrations.garminconnect_oauth1,
            user_integrations.garminconnect_oauth2,
        )
        return garminconnect_client
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_user_garminconnect_client: {err}", "error", exc=err
        )
        return None

def get_user_garminconnect_activities_by_dates(
    start_date: datetime, end_date: datetime, user_id: int, db: Session # Added end_date
) -> list[activities_schema.Activity] | None:
    try:
        garminconnect_client = get_user_garminconnect_client(user_id, db)
        if garminconnect_client is not None:
            garminconnect_activities_processed = fetch_and_process_activities_by_dates(
                garminconnect_client, start_date, end_date, user_id, db
            )
            core_logger.print_to_log(
                f"User {user_id}: Started Garmin Connect activities processing for date range {start_date.date()} to {end_date.date()}"
            )
            count = len(garminconnect_activities_processed) if garminconnect_activities_processed else 0
            core_logger.print_to_log(
                f"User {user_id}: {count} Garmin Connect activities processed"
            )
            return garminconnect_activities_processed
        return None
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_user_garminconnect_activities_by_dates: {err}",
            "error",
            exc=err,
        )
        return None
