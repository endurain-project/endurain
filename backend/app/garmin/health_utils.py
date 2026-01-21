import os
import zipfile

from datetime import datetime, timedelta, date, timezone
import garminconnect
from sqlalchemy.orm import Session

import core.logger as core_logger

import garmin.utils as garmin_utils

import health.health_weight.crud as health_weight_crud
import health.health_weight.schema as health_weight_schema

import health.health_steps.crud as health_steps_crud
import health.health_steps.schema as health_steps_schema

import health.health_sleep.crud as health_sleep_crud
import health.health_sleep.schema as health_sleep_schema

import users.users.crud as users_crud

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
        # Validate metabolic_age is a reasonable value (1-150 years)
        metabolic_age = bc.get("metabolicAge")
        if metabolic_age is not None and (metabolic_age < 1 or metabolic_age > 150):
            metabolic_age = None

        health_weight = health_weight_schema.HealthWeightBase(
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
            metabolic_age=metabolic_age,
            source=health_weight_schema.Source.GARMIN,
        )

        health_weight_db = health_weight_crud.get_health_weight_by_date(
            user_id, str(health_weight.date), db
        )

        if health_weight_db:
            # Convert to update schema with the existing ID
            health_weight_update = health_weight_schema.HealthWeightUpdate(
                id=health_weight_db.id, user_id=user_id, **health_weight.model_dump()
            )
            # Updates the health_weight in the database
            health_weight_crud.edit_health_weight(user_id, health_weight_update, db)
            core_logger.print_to_log(
                f"User {user_id}: Body composition edited for date {health_weight.date}"
            )
        else:
            # Convert to update schema with the existing ID
            health_weight_create = health_weight_schema.HealthWeightCreate(
                **health_weight.model_dump()
            )
            # Creates the health_weight in the database
            health_weight_crud.create_health_weight(user_id, health_weight_create, db)
            core_logger.print_to_log(
                f"User {user_id}: Body composition created for date {health_weight.date}"
            )
        # Increment the count of processed body composition
        count_processed += 1
    # Return the count of processed body composition
    return count_processed


def fetch_and_process_ds_by_dates(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    db: Session,
) -> int:
    try:
        # Fetch Garmin Connect daily steps data for the specified date range
        garmin_ds = garminconnect_client.get_daily_steps(
            str(start_date.date()), str(end_date.date())
        )
    except Exception as err:
        # Log an informational event if no daily steps were found
        core_logger.print_to_log(
            f"Error fetching daily steps for user {user_id} between {start_date.date()} and {end_date.date()}: {err}",
            "error",
            exc=err,
        )
        # Return 0 to indicate no daily steps were processed
        return 0

    if (
        garmin_ds is None
        or "totalSteps" not in garmin_ds[0]
        or not garmin_ds[0]["totalSteps"]
    ):
        # Log an informational event if no daily steps were found
        core_logger.print_to_log_and_console(
            f"User {user_id}: No new Garmin Connect daily steps found between {start_date.date()} and {end_date.date()}: garmin_ds is None or empty"
        )
        # Return 0 to indicate no daily steps were processed
        return 0

    # Set the count of processed steps to 0
    count_processed = 0
    # Process steps
    for ds in garmin_ds:
        if ds["totalSteps"] is None:
            continue

        health_steps = health_steps_schema.HealthStepsBase(
            date=ds["calendarDate"],
            steps=ds["totalSteps"],
            source=health_steps_schema.Source.GARMIN,
        )

        health_steps_db = health_steps_crud.get_health_steps_by_date(
            user_id, str(health_steps.date), db
        )

        if health_steps_db:
            # Convert to update schema with the existing ID
            health_steps_update = health_steps_schema.HealthStepsUpdate(
                id=health_steps_db.id, user_id=user_id, **health_steps.model_dump()
            )
            # Updates the health_steps in the database
            health_steps_crud.edit_health_steps(user_id, health_steps_update, db)
            core_logger.print_to_log(
                f"User {user_id}: Daily steps edited for date {health_steps.date}"
            )
        else:
            # Convert to update schema with the existing ID
            health_steps_create = health_steps_schema.HealthStepsCreate(
                **health_steps.model_dump()
            )
            # Creates the health_steps in the database
            health_steps_crud.create_health_steps(user_id, health_steps_create, db)
            core_logger.print_to_log(
                f"User {user_id}: Daily steps created for date {health_steps.date}"
            )
        # Increment the count of processed steps
        count_processed += 1
    # Return the count of processed steps
    return count_processed


def fetch_and_process_sleep_by_dates(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    db: Session,
) -> int:
    """
    Fetch and process sleep data from Garmin Connect.

    Args:
        garminconnect_client: Authenticated Garmin Connect client.
        start_date: Start date for sleep data retrieval.
        end_date: End date for sleep data retrieval.
        user_id: ID of the user to process sleep data for.
        db: Database session.

    Returns:
        Number of sleep records processed.
    """
    count_processed = 0
    current_date = start_date

    # Iterate through each date since get_sleep_data only supports
    # single date
    while current_date <= end_date:
        date_string = current_date.strftime("%Y-%m-%d")

        try:
            garmin_sleep = garminconnect_client.get_sleep_data(date_string)
        except Exception as err:
            core_logger.print_to_log(
                f"Error fetching sleep data for user "
                f"{user_id} on {date_string}: {err}",
                "error",
                exc=err,
            )
            current_date += timedelta(days=1)
            continue

        if (
            garmin_sleep is None
            or "dailySleepDTO" not in garmin_sleep
            or not garmin_sleep["dailySleepDTO"]
        ):
            core_logger.print_to_log(
                f"User {user_id}: No Garmin Connect sleep data "
                f"found for {date_string}"
            )
            current_date += timedelta(days=1)
            continue

        sleep_dto = garmin_sleep["dailySleepDTO"]

        # Convert timestamps from milliseconds to datetime
        sleep_start_gmt = (
            datetime.fromtimestamp(
                sleep_dto["sleepStartTimestampGMT"] / 1000,
                tz=timezone.utc,
            )
            if sleep_dto.get("sleepStartTimestampGMT")
            else None
        )
        sleep_end_gmt = (
            datetime.fromtimestamp(
                sleep_dto["sleepEndTimestampGMT"] / 1000,
                tz=timezone.utc,
            )
            if sleep_dto.get("sleepEndTimestampGMT")
            else None
        )
        sleep_start_local = (
            datetime.fromtimestamp(
                sleep_dto["sleepStartTimestampLocal"] / 1000,
                tz=timezone.utc,
            )
            if sleep_dto.get("sleepStartTimestampLocal")
            else None
        )
        sleep_end_local = (
            datetime.fromtimestamp(
                sleep_dto["sleepEndTimestampLocal"] / 1000,
                tz=timezone.utc,
            )
            if sleep_dto.get("sleepEndTimestampLocal")
            else None
        )

        # Process sleep stages from sleepLevels array
        sleep_stages = []
        if "sleepLevels" in garmin_sleep and garmin_sleep["sleepLevels"]:
            for level in garmin_sleep["sleepLevels"]:
                activity_level = level.get("activityLevel")

                # Validate and convert activity_level to enum
                try:
                    # Map Garmin activity levels to sleep stage types
                    # 0=deep, 1=light, 2=REM, 3=awake
                    stage_type = health_sleep_schema.SleepStageType(activity_level)
                except (TypeError, ValueError):
                    # Skip unknown or missing levels
                    continue

                start_gmt_str = level.get("startGMT")
                end_gmt_str = level.get("endGMT")

                start_gmt = (
                    datetime.strptime(
                        start_gmt_str,
                        "%Y-%m-%dT%H:%M:%S.%f",
                    ).replace(tzinfo=timezone.utc)
                    if start_gmt_str
                    else None
                )
                end_gmt = (
                    datetime.strptime(
                        end_gmt_str,
                        "%Y-%m-%dT%H:%M:%S.%f",
                    ).replace(tzinfo=timezone.utc)
                    if end_gmt_str
                    else None
                )

                duration_seconds = None
                if start_gmt and end_gmt:
                    duration_seconds = int((end_gmt - start_gmt).total_seconds())

                sleep_stage = health_sleep_schema.HealthSleepStage(
                    stage_type=stage_type,
                    start_time_gmt=start_gmt,
                    end_time_gmt=end_gmt,
                    duration_seconds=duration_seconds,
                )
                sleep_stages.append(sleep_stage)

        # Extract sleep scores
        sleep_scores = sleep_dto.get("sleepScores", {})
        overall_score = sleep_scores.get("overall", {})
        total_duration_score = sleep_scores.get(
            "totalDuration",
            {},
        )
        awake_count_score = sleep_scores.get("awakeCount", {})
        deep_percentage_score = sleep_scores.get(
            "deepPercentage",
            {},
        )
        light_percentage_score = sleep_scores.get(
            "lightPercentage",
            {},
        )
        rem_percentage_score = sleep_scores.get(
            "remPercentage",
            {},
        )
        sleep_stress_score = sleep_scores.get("stress", {})

        health_sleep = health_sleep_schema.HealthSleepBase(
            date=sleep_dto["calendarDate"],
            sleep_start_time_gmt=sleep_start_gmt,
            sleep_end_time_gmt=sleep_end_gmt,
            sleep_start_time_local=sleep_start_local,
            sleep_end_time_local=sleep_end_local,
            total_sleep_seconds=sleep_dto.get("sleepTimeSeconds"),
            nap_time_seconds=sleep_dto.get("napTimeSeconds"),
            unmeasurable_sleep_seconds=sleep_dto.get("unmeasurableSleepSeconds"),
            deep_sleep_seconds=sleep_dto.get("deepSleepSeconds"),
            light_sleep_seconds=sleep_dto.get("lightSleepSeconds"),
            rem_sleep_seconds=sleep_dto.get("remSleepSeconds"),
            awake_sleep_seconds=sleep_dto.get("awakeSleepSeconds"),
            avg_heart_rate=(
                int(sleep_dto.get("avgHeartRate"))
                if sleep_dto.get("avgHeartRate") is not None
                else None
            ),
            min_heart_rate=None,
            max_heart_rate=None,
            avg_spo2=(
                int(sleep_dto.get("averageSpO2Value"))
                if sleep_dto.get("averageSpO2Value") is not None
                else None
            ),
            lowest_spo2=sleep_dto.get("lowestSpO2Value"),
            highest_spo2=sleep_dto.get("highestSpO2Value"),
            avg_respiration=(
                int(sleep_dto.get("averageRespirationValue"))
                if sleep_dto.get("averageRespirationValue") is not None
                else None
            ),
            lowest_respiration=(
                int(sleep_dto.get("lowestRespirationValue"))
                if sleep_dto.get("lowestRespirationValue") is not None
                else None
            ),
            highest_respiration=(
                int(sleep_dto.get("highestRespirationValue"))
                if sleep_dto.get("highestRespirationValue") is not None
                else None
            ),
            avg_stress_level=(
                int(sleep_dto.get("avgSleepStress"))
                if sleep_dto.get("avgSleepStress") is not None
                else None
            ),
            awake_count=sleep_dto.get("awakeCount"),
            restless_moments_count=None,
            sleep_score_overall=overall_score.get("value"),
            sleep_score_duration=total_duration_score.get("qualifierKey"),
            sleep_score_quality=overall_score.get("qualifierKey"),
            garminconnect_sleep_id=str(sleep_dto.get("id")),
            sleep_stages=sleep_stages if sleep_stages else None,
            source=health_sleep_schema.Source.GARMIN,
            hrv_status=(
                health_sleep_schema.HRVStatus(garmin_sleep.get("hrvStatus"))
                if garmin_sleep.get("hrvStatus")
                and garmin_sleep.get("hrvStatus")
                in health_sleep_schema.HRVStatus._value2member_map_
                else None
            ),
            resting_heart_rate=garmin_sleep.get("restingHeartRate"),
            avg_skin_temp_deviation=garmin_sleep.get("avgSkinTempDeviationC"),
            awake_count_score=(
                health_sleep_schema.SleepScore(awake_count_score.get("qualifierKey"))
                if awake_count_score
                and awake_count_score.get("qualifierKey")
                in health_sleep_schema.SleepScore._value2member_map_
                else None
            ),
            rem_percentage_score=(
                health_sleep_schema.SleepScore(rem_percentage_score.get("qualifierKey"))
                if rem_percentage_score
                and rem_percentage_score.get("qualifierKey")
                in health_sleep_schema.SleepScore._value2member_map_
                else None
            ),
            deep_percentage_score=(
                health_sleep_schema.SleepScore(
                    deep_percentage_score.get("qualifierKey")
                )
                if deep_percentage_score
                and deep_percentage_score.get("qualifierKey")
                in health_sleep_schema.SleepScore._value2member_map_
                else None
            ),
            light_percentage_score=(
                health_sleep_schema.SleepScore(
                    light_percentage_score.get("qualifierKey")
                )
                if light_percentage_score
                and light_percentage_score.get("qualifierKey")
                in health_sleep_schema.SleepScore._value2member_map_
                else None
            ),
            avg_sleep_stress=(
                int(sleep_dto.get("avgSleepStress"))
                if sleep_dto.get("avgSleepStress") is not None
                else None
            ),
            sleep_stress_score=(
                health_sleep_schema.SleepScore(sleep_stress_score.get("qualifierKey"))
                if sleep_stress_score
                and sleep_stress_score.get("qualifierKey")
                in health_sleep_schema.SleepScore._value2member_map_
                else None
            ),
        )

        health_sleep_db = health_sleep_crud.get_health_sleep_by_date(
            user_id, str(health_sleep.date), db
        )

        if health_sleep_db:
            # Convert to update schema with the existing ID
            health_sleep_update = health_sleep_schema.HealthSleepUpdate(
                id=health_sleep_db.id, user_id=user_id, **health_sleep.model_dump()
            )
            # Updates the health_sleep in the database
            health_sleep_crud.edit_health_sleep(user_id, health_sleep_update, db)
            core_logger.print_to_log(
                f"User {user_id}: Sleep data edited for date " f"{health_sleep.date}"
            )
        else:
            # Convert to update schema with the existing ID
            health_sleep_create = health_sleep_schema.HealthSleepCreate(
                **health_sleep.model_dump()
            )
            # Creates the health_sleep in the database
            health_sleep_crud.create_health_sleep(user_id, health_sleep_create, db)
            core_logger.print_to_log(
                f"User {user_id}: Sleep data created for date " f"{health_sleep.date}"
            )

        count_processed += 1
        current_date += timedelta(days=1)

    return count_processed


def retrieve_garminconnect_users_health_for_days(days: int):
    # Create a new database session using context manager
    with SessionLocal() as db:
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
                    get_user_garminconnect_health_by_dates(
                        calculated_start_date,
                        calculated_end_date,
                        user.id,
                    )
                except Exception as err:
                    core_logger.print_to_log(
                        f"Error processing health data for user {user.id} in retrieve_garminconnect_users_health_for_days: {err}",
                        "error",
                        exc=err,
                    )
        except Exception as err:
            core_logger.print_to_log(
                f"Error getting users in retrieve_garminconnect_users_health_for_days: {err}",
                "error",
                exc=err,
            )


def get_user_garminconnect_health_by_dates(
    start_date: datetime, end_date: datetime, user_id: int
):
    # Create a new database session using context manager
    with SessionLocal() as db:
        try:
            # Get the user integrations by user ID
            user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(
                user_id, db
            )

            if user_integrations is None:
                core_logger.print_to_log(f"User {user_id}: Garmin Connect not linked")
                return None

            # Log the start of the health processing
            core_logger.print_to_log(
                f"User {user_id}: Started Garmin Connect health processing for date range {start_date.date()} to {end_date.date()}"
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

            # Fetch Garmin Connect daily steps for the specified date range
            num_garminconnect_ds_processed = fetch_and_process_ds_by_dates(
                garminconnect_client, start_date, end_date, user_id, db
            )

            num_garminconnect_sleep_processed = fetch_and_process_sleep_by_dates(
                garminconnect_client, start_date, end_date, user_id, db
            )

            core_logger.print_to_log(
                f"User {user_id}: {num_garminconnect_bc_processed} Garmin Connect body composition processed"
            )
            core_logger.print_to_log(
                f"User {user_id}: {num_garminconnect_ds_processed} Garmin Connect daily steps processed"
            )
            core_logger.print_to_log(
                f"User {user_id}: {num_garminconnect_sleep_processed} Garmin Connect sleep data processed"
            )
        except Exception as err:
            core_logger.print_to_log(
                f"Error in get_user_garminconnect_health_by_dates: {err}",
                "error",
                exc=err,
            )
