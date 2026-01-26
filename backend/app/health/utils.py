import os
import asyncio

import time
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status, UploadFile

from sqlalchemy.orm import Session

import health.schema as health_schema
import health.health_intraday_steps.crud as health_intraday_steps_crud
import health.health_intraday_steps.schema as health_intraday_steps_schema
import health.health_intraday_steps.models as health_intraday_steps_models
import health.health_intraday_heart_rate.crud as health_intraday_heart_rate_crud
import health.health_intraday_heart_rate.schema as health_intraday_heart_rate_schema
import health.health_intraday_heart_rate.models as health_intraday_heart_rate_models
import health.health_sleep.crud as health_sleep_crud
import health.health_sleep.schema as health_sleep_schema
import health.health_sleep.models as health_sleep_models

import users.users.crud as users_crud

import users.users_privacy_settings.crud as users_privacy_settings_crud

import websocket.manager as websocket_manager

import core.logger as core_logger
import core.config as core_config
import core.database as core_database

import activities.activity.utils as activity_utils


async def parse_and_store_health_from_uploaded_file(
    token_user_id: int,
    file: UploadFile,
    db: Session,
):
    # Validate filename exists
    if file.filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Get file extension
    _, file_extension = os.path.splitext(file.filename)

    try:
        # Ensure the 'files' directory exists
        upload_dir = core_config.FILES_DIR
        os.makedirs(upload_dir, exist_ok=True)

        # Build the full path where the file will be saved
        file_path = os.path.join(upload_dir, file.filename)

        # Save the uploaded file in the 'files' directory
        with open(file_path, "wb") as save_file:
            save_file.write(file.file.read())

        if file_extension.lower() == ".gz":
            file_path, file_extension = activity_utils.handle_gzipped_file(file_path)

        user = users_crud.get_user_by_id(token_user_id, db)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user_privacy_settings = (
            users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                user.id, db
            )
        )

        created_intraday_steps = []
        created_intraday_heart_rate = []
        updated_sleep = None
        if file_extension.lower() == ".fit":
            # Parse the file
            parsed_info = activity_utils.parse_file(
                token_user_id,
                user_privacy_settings,
                file_extension,
                file_path,
                db,
            )

            intraday_steps, intraday_heart_rate, sleep = process_info(parsed_info)

            # Set the source
            for step in intraday_steps:
                step.source = health_intraday_steps_schema.Source.GARMIN
            for heart_rate in intraday_heart_rate:
                heart_rate.source = health_intraday_heart_rate_schema.Source.GARMIN
            sleep.source = health_sleep_schema.Source.GARMIN
            
            # Store step data in the database
            if intraday_steps:
                created_intraday_steps = await store_intraday_steps(
                    intraday_steps, db, user.id,
                )

            # Store heart rate data in the database
            if intraday_heart_rate:
                created_intraday_heart_rate = await store_intraday_heart_rate(
                    intraday_heart_rate, db, user.id
                )

            # Update resting heart rate data in the database
            if sleep:
                updated_sleep = await update_sleep(
                    sleep, db, user.id
                )
        else:
            core_logger.print_to_log_and_console(
                f"File extension not supported: {file_extension}", "error"
            )

        # Define the directory where the processed files will be stored
        processed_dir = core_config.FILES_PROCESSED_DIR

        # Move the file to the processed directory
        new_file_name = f"{parsed_info.get("file_id")}_{os.path.basename(file_path)}"
        activity_utils.move_file(processed_dir, new_file_name, file_path)

        # Serialize results.
        for i, steps in enumerate(created_intraday_steps):
            created_intraday_steps[i] = serialize_intraday_steps(steps)
        for i, heart_rate in enumerate(created_intraday_heart_rate):
            created_intraday_heart_rate[i] = serialize_intraday_heart_rate(heart_rate)
        updated_sleep = serialize_updated_resting_heart_rate(updated_sleep)

        return create_health_import_response(
            created_intraday_steps, 
            created_intraday_heart_rate, 
            updated_sleep,
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in parse_and_store_health_from_uploaded_file - {str(err)}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(err)}",
        ) from err


def create_health_import_response(
    created_intraday_steps: list[health_intraday_steps_models.HealthIntradaySteps], 
    created_intraday_heart_rate: list[health_intraday_heart_rate_models.HealthIntradayHeartrate],
    updated_sleep: health_sleep_models.HealthSleep | None
):
    created_intraday_steps = [
        health_intraday_steps_schema.HealthIntradayStepsRead.model_validate(step, from_attributes=True)
        for step in created_intraday_steps
    ]

    created_intraday_heart_rate = [
        health_intraday_heart_rate_schema.HealthIntradayHeartrateRead.model_validate(hr, from_attributes=True)
        for hr in created_intraday_heart_rate
    ]   

    updated_sleep = health_sleep_schema.HealthSleepRead.model_validate(updated_sleep, from_attributes=True) if updated_sleep else None

    return health_schema.HealthImportResponse(
        created_intraday_step_records=created_intraday_steps,
        created_intraday_heart_rate_records=created_intraday_heart_rate,
        updated_sleep=updated_sleep,
    )


def process_info(parsed_info: dict) -> tuple[
    list[health_intraday_steps_schema.HealthIntradayStepsCreate], 
    list[health_intraday_heart_rate_schema.HealthIntradayHeartrateCreate],
    dict,
]: 
    steps = parsed_info.get("intraday_steps") or []
    intraday_steps = [
        health_intraday_steps_schema.HealthIntradayStepsCreate(
            timestamp=info["timestamp"],
            steps=info["steps"],
            intensity=info.get("intensity"),
            distance=info.get("distance"),
            activity_type=activity_utils.define_activity_type(info.get("activity_type")),
        )
        for info in steps
    ]

    heart_rates = parsed_info.get("intraday_heart_rate") or []
    intraday_heart_rate = [
        health_intraday_heart_rate_schema.HealthIntradayHeartrateCreate(
            timestamp=info["timestamp"],
            heart_rate=info["heart_rate"],
        )
        for info in heart_rates
    ]

    # Update the resting heart rate in sleep stats
    rhr_info = parsed_info.get("resting_heart_rate")
    sleep = health_sleep_schema.HealthSleepCreate(
        date=rhr_info["timestamp"].date(),
        resting_heart_rate=rhr_info["current_day_resting_heart_rate"]
    ) if rhr_info else None

    return intraday_steps, intraday_heart_rate, sleep


async def store_intraday_steps(
    intraday_steps: list[health_intraday_steps_schema.HealthIntradayStepsCreate],
    db: Session,
    user_id: int,
):
    created_steps = health_intraday_steps_crud.create_health_intraday_steps(
        user_id, intraday_steps, db
    )

    # Check if created_steps is None
    if created_steps is None or any(steps.id is None for steps in created_steps):
        # Log the error
        core_logger.print_to_log(
            "Error in store_intraday_steps - intraday steps is None, error creating intraday steps",
            "error",
        )
        # raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating intraday steps",
        )
    
    # Return the created steps
    return created_steps


async def store_intraday_heart_rate(
    intraday_heart_rate: list[health_intraday_heart_rate_schema.HealthIntradayHeartrateCreate],
    db: Session,
    user_id: int,
):
    created_heart_rate = health_intraday_heart_rate_crud.create_health_intraday_heart_rate(
        user_id, intraday_heart_rate, db
    )

    # Check if created_heart_rate is None
    if created_heart_rate is None or any(heart_rate.id is None for heart_rate in created_heart_rate):
        # Log the error
        core_logger.print_to_log(
            "Error in store_intraday_heart_rate - intraday heart_rate is None, error creating intraday heart_rate",
            "error",
        )
        # raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating intraday heart_rate",
        )
    
    # Return the created heart_rate
    return created_heart_rate


async def update_sleep(
    sleep: health_sleep_schema.HealthSleepCreate,
    db: Session,
    user_id: int,
):
    # Check if a sleep entry for this date already exists for this date
    existing_sleep = health_sleep_crud.get_sleep_by_date_and_user(user_id, sleep.date, db)
    if existing_sleep:
        sleep_update = health_sleep_schema.HealthSleepUpdate(
            id=existing_sleep.id,
            user_id=existing_sleep.user_id,
            resting_heart_rate=sleep.resting_heart_rate,
        )
        updated_sleep = health_sleep_crud.edit_health_sleep(user_id, sleep, db)
    else:
        updated_sleep = health_sleep_crud.create_health_sleep(user_id, sleep, db)

    # Check if updated_resting_heart_rate is None
    if updated_sleep is None or updated_sleep.id is None:
        # Log the error
        core_logger.print_to_log(
            "Error in update_sleep - intraday heart_rate is None, error creating intraday heart_rate",
            "error",
        )
        # raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating resting heart rate",
        )
    
    # Return the created heart_rate
    return updated_sleep


def serialize_intraday_steps(steps: health_intraday_steps_models.HealthIntradaySteps):
    timezone =  ZoneInfo(os.environ.get("TZ", "UTC"))
    steps.timestamp = activity_utils.make_aware_and_format(
        steps.timestamp, timezone
    )
    # Convert to datetime objects if they are strings before calling astimezone
    timestamp_dt = activity_utils.convert_to_datetime_if_string(steps.timestamp)
    steps.timestamp = timestamp_dt.astimezone(None).strftime("%Y-%m-%dT%H:%M:%S")
    return steps


def serialize_intraday_heart_rate(heart_rate: health_intraday_heart_rate_models.HealthIntradayHeartrate):
    timezone =  ZoneInfo(os.environ.get("TZ", "UTC"))
    heart_rate.timestamp = activity_utils.make_aware_and_format(
        heart_rate.timestamp, timezone
    )
    # Convert to datetime objects if they are strings before calling astimezone
    timestamp_dt = activity_utils.convert_to_datetime_if_string(heart_rate.timestamp)
    heart_rate.timestamp = timestamp_dt.astimezone(None).strftime("%Y-%m-%dT%H:%M:%S")
    return heart_rate


def serialize_updated_resting_heart_rate(sleep: health_sleep_models.HealthSleep):
    timezone =  ZoneInfo(os.environ.get("TZ", "UTC"))
    sleep.date = activity_utils.make_aware_and_format(
        sleep.date, timezone
    )
    # Convert to datetime objects if they are strings before calling astimezone
    timestamp_dt = activity_utils.convert_to_datetime_if_string(sleep.date)
    sleep.date = timestamp_dt.astimezone(None).strftime("%Y-%m-%d")
    return sleep