import os
import zipfile

from datetime import datetime, timedelta, date, timezone
import garminconnect
from sqlalchemy.orm import Session

import core.logger as core_logger

import garmin.utils as garmin_utils

import health_data.crud as health_data_crud
import health_data.schema as health_data_schema

import users.user.crud as users_crud

from core.database import SessionLocal


def fetch_and_process_bc_by_dates(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    db: Session,
) -> int:
    try:
        # Fetch Garmin Connect body composition data for the specified date range
        garmin_bc = garminconnect_client.get_body_composition(
            str(start_date.date()), str(end_date.date())
        )
    except Exception as err:
        # Log an informational event if no body composition were found
        core_logger.print_to_log(
            f"Error fetching body composition for user {user_id} between {start_date.date()} and {end_date.date()}: {err}",
            "error",
            exc=err,
        )
        # Return 0 to indicate no body composition were processed
        return 0

    if (
        garmin_bc is None
        or "dateWeightList" not in garmin_bc
        or not garmin_bc["dateWeightList"]
    ):
        # Log an informational event if no body composition were found
        core_logger.print_to_log_and_console(
            f"User {user_id}: No new Garmin Connect body composition found between {start_date.date()} and {end_date.date()}: garmin_bc is None or empty"
        )
        # Return 0 to indicate no body composition were processed
        return 0

    # Set the count of processed body composition to 0
    count_processed = 0
    # Process body composition
    for bc in garmin_bc["dateWeightList"]:
        health_data = health_data_schema.HealthData(
            user_id=user_id,
            date=bc["calendarDate"],
            weight=bc["weight"] / 1000 if bc["weight"] is not None else None,
            bmi=bc["bmi"],
            body_fat=bc["bodyFat"],
            body_water=bc["bodyWater"],
            bone_mass=(bc["boneMass"] / 1000 if bc["boneMass"] is not None else None),
            muscle_mass=(
                bc["muscleMass"] / 1000 if bc["muscleMass"] is not None else None
            ),
            physique_rating=bc["physiqueRating"],
            visceral_fat=bc["visceralFat"],
            metabolic_age=bc["metabolicAge"],
            garminconnect_body_composition_id=str(bc["samplePk"]),
        )

        health_data_db = health_data_crud.get_health_data_by_date(
            user_id, health_data.date, db
        )

        if health_data_db:
            health_data.id = health_data_db.id
            health_data_crud.edit_health_data(user_id, health_data, db)
            core_logger.print_to_log(
                f"User {user_id}: Body composition edited for date {health_data.date}"
            )
        else:
            health_data_crud.create_health_data(user_id, health_data, db)
            core_logger.print_to_log(
                f"User {user_id}: Body composition created for date {health_data.date}"
            )
        # Increment the count of processed body composition
        count_processed += 1
    # Return the count of processed body composition
    return count_processed


def retrieve_garminconnect_users_bc_for_days(days: int):
    # Create a new database session
    db = SessionLocal()
    try:
        # Get all users
        users = users_crud.get_all_users(db)
        # Calculate the start and end dates
        calculated_start_date = datetime.now(timezone.utc) - timedelta(days=days)
        calculated_end_date = datetime.now(timezone.utc)

        # Iterate through all users
        for user in users:
            try:
                # Get the user's Garmin Connect body composition data
                get_user_garminconnect_bc_by_dates(
                    calculated_start_date,
                    calculated_end_date,
                    user.id,
                )
            except Exception as err:
                core_logger.print_to_log(
                    f"Error processing body composition for user {user.id} in retrieve_garminconnect_users_bc_for_days: {err}",
                    "error",
                    exc=err,
                )
    except Exception as err:
        core_logger.print_to_log(
            f"Error getting users in retrieve_garminconnect_users_bc_for_days: {err}",
            "error",
            exc=err,
        )
    finally:
        # Ensure the session is closed after use
        db.close()


def get_user_garminconnect_bc_by_dates(
    start_date: datetime, end_date: datetime, user_id: int
):
    # Create a new database session
    db = SessionLocal()
    try:
        # Get the user integrations by user ID
        user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(
            user_id, db
        )

        if user_integrations is None:
            core_logger.print_to_log(f"User {user_id}: Garmin Connect not linked")
            return None

        # Log the start of the body composition processing
        core_logger.print_to_log(
            f"User {user_id}: Started Garmin Connect body composition processing for date range {start_date.date()} to {end_date.date()}"
        )

        # Create a Garmin Connect client with the user's access token
        garminconnect_client = garmin_utils.login_garminconnect_using_tokens(
            user_integrations.garminconnect_oauth1,
            user_integrations.garminconnect_oauth2,
        )

        # Fetch Garmin Connect body composition for the specified date range
        num_garminconnect_bc_processed = fetch_and_process_bc_by_dates(
            garminconnect_client, start_date, end_date, user_id, db
        )

        core_logger.print_to_log(
            f"User {user_id}: {num_garminconnect_bc_processed} Garmin Connect body composition processed"
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_user_garminconnect_bc_by_dates: {err}",
            "error",
            exc=err,
        )
    finally:
        # Ensure the session is closed after use
        db.close()
