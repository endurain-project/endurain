import os
import zipfile

from datetime import datetime, timedelta, date, timezone
import garminconnect
from sqlalchemy.orm import Session

import core.logger as core_logger

import garmin.utils as garmin_utils

import health_data.crud as health_data_crud
import health_data.schema as health_data_schema

import users.crud as users_crud

from core.database import SessionLocal


def fetch_and_process_bc(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    user_id: int,
    db: Session,
) -> int:
    # Fetch Garmin Connect body composition after the specified start date
    garmin_bc = garminconnect_client.get_body_composition(start_date, date.today())

    if garmin_bc is None:
        # Log an informational event if no body composition were found
        core_logger.print_to_log_and_console(
            f"User {user_id}: No new Garmin Connect body composition found after {start_date}: garmin_bc is None"
        )

        # Return 0 to indicate no body composition were processed
        return 0

    # Process body composition
    for bc in garmin_bc["dateWeightList"]:
        health_data = health_data_schema.HealthData(
            user_id=user_id,
            date=bc["calendarDate"],
            weight=bc["weight"] / 1000,
            bmi=bc["bmi"],
            #body_fat=bc["bodyFat"],
            #body_water=bc["bodyWater"],
            #bone_mass=bc["boneMass"],
            #muscle_mass=bc["muscleMass"],
            #physique_rating=bc["physiqueRating"],
            #visceral_fat=bc["visceralFat"],
            #metabolic_age=bc["metabolicAge"],
            garminconnect_body_composition_id=str(bc["samplePk"]),
        )

        # Check if the body composition is already stored in the database
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

    # Return the number of body compositions processed
    return len(garmin_bc["dateWeightList"])


def retrieve_garminconnect_users_bc_for_days(days: int):
    # Create a new database session
    db = SessionLocal()

    try:
        # Get all users
        users = users_crud.get_all_users(db)
    finally:
        # Ensure the session is closed after use
        db.close()

    # Process the body composition for each user
    for user in users:
        get_user_garminconnect_bc_by_days(
            (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
            user.id,
        )


def get_user_garminconnect_bc_by_days(start_date: datetime, user_id: int):
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
            f"User {user_id}: Started Garmin Connect body composition processing"
        )

        # Create a Garmin Connect client with the user's access token
        garminconnect_client = garmin_utils.login_garminconnect_using_tokens(
            user_integrations.garminconnect_oauth1,
            user_integrations.garminconnect_oauth2,
        )

        # Fetch Garmin Connect body composition after the specified start date
        num_garminconnect_bc_processed = fetch_and_process_bc(
            garminconnect_client, start_date, user_id, db
        )

        # Log an informational event for tracing
        core_logger.print_to_log(
            f"User {user_id}: {num_garminconnect_bc_processed} Garmin Connect body composition processed"
        )
    finally:
        # Ensure the session is closed after use
        db.close()
