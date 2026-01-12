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

import users.user.crud as users_crud

import users.user_privacy_settings.crud as users_privacy_settings_crud

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
        if file_extension.lower() == ".fit":
            # Parse the file
            parsed_info = activity_utils.parse_file(
                token_user_id,
                user_privacy_settings,
                file_extension,
                file_path,
                db,
            )

            intraday_steps, intraday_heart_rate, resting_heart_rate = process_info(parsed_info)

            # Set the source
            for step in intraday_steps:
                step.source = health_intraday_steps_schema.Source.GARMIN
            for heart_rate in intraday_heart_rate:
                heart_rate.source = health_intraday_heart_rate_schema.Source.GARMIN

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
        else:
            core_logger.print_to_log_and_console(
                f"File extension not supported: {file_extension}", "error"
            )

        # Define the directory where the processed files will be stored
        processed_dir = core_config.FILES_PROCESSED_DIR

        # TODO: Add random uploaded time to this file to deduplicate
        new_file_name = os.path.basename(file_path)

        # Move the file to the processed directory
        activity_utils.move_file(processed_dir, new_file_name, file_path)

        # Serialize results.
        for i, steps in enumerate(created_intraday_steps):
            created_intraday_steps[i] = serialize_intraday_steps(steps)
        for i, heart_rate in enumerate(created_intraday_heart_rate):
            created_intraday_heart_rate[i] = serialize_intraday_heart_rate(heart_rate)

        return create_health_import_response(created_intraday_steps, created_intraday_heart_rate)
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
    created_intraday_heart_rate: list[health_intraday_heart_rate_models.HealthIntradayHeartrate]
):
    created_intraday_steps = [
        health_intraday_steps_schema.HealthIntradayStepsRead.model_validate(step, from_attributes=True)
        for step in created_intraday_steps
    ]

    created_intraday_heart_rate = [
        health_intraday_heart_rate_schema.HealthIntradayHeartrateRead.model_validate(hr, from_attributes=True)
        for hr in created_intraday_heart_rate
    ]   

    return health_schema.HealthImportResponse(
        created_intraday_step_records=created_intraday_steps,
        created_intraday_heart_rate_records=created_intraday_heart_rate,
    )


def process_info(parsed_info: dict) -> tuple[
    list[health_intraday_steps_schema.HealthIntradayStepsCreate], 
    list[health_intraday_heart_rate_schema.HealthIntradayHeartrateCreate],
    dict,
]: 
    # Convert steps from cumulative step counts to delta step counts
    # Assumes steps are in message frame order as produced in the .fit file, 
    # meaning the steps should be monotonically increasing regardless of the timestamp.
    steps = parsed_info.get("intraday_steps") or []
    last_step_count = 0
    for info in steps:
        delta_count = info["steps"] - last_step_count
        last_step_count = info["steps"]
        info["steps"] = delta_count

    intraday_steps = [
        health_intraday_steps_schema.HealthIntradayStepsCreate(
            timestamp=info["timestamp"],
            steps=info["steps"],
            intensity=info.get("intensity"),
            activity_type=activity_utils.define_activity_type(info.get("activity_type")),
        )
        for info in steps
        # Remove any entries without an increase in steps (e.g, the final record 
        # which is typically a summary that we don't need)
        if info["steps"] > 0
    ]

    heart_rates = parsed_info.get("intraday_heart_rate") or []
    intraday_heart_rate = [
        health_intraday_heart_rate_schema.HealthIntradayHeartrateCreate(
            timestamp=info["timestamp"],
            heart_rate=info["heart_rate"],
        )
        for info in heart_rates
    ]

    # TODO: Convert this to the schema object for resting heart rate
    resting_heart_rate = parsed_info["resting_heart_rate"]

    return intraday_steps, intraday_heart_rate, resting_heart_rate


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
    
    # TODO: Also add regular steps entry for relevant day

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


# TODO: Implement
#def process_all_files_sync(
#    user_id: int,
#    file_paths: list[str],
#    websocket_manager: websocket_manager.WebSocketManager,
#):
#    """
#    Process all files sequentially in single thread.
#
#    Args:
#        user_id: User ID.
#        file_paths: List of file paths to process.
#        websocket_manager: WebSocket manager instance.
#    """
#    db = next(core_database.get_db())
#    try:
#        total_files = len(file_paths)
#        for idx, file_path in enumerate(file_paths, 1):
#            core_logger.print_to_log_and_console(
#                f"Processing file {idx}/{total_files}: " f"{file_path}"
#            )
#            asyncio.run(
#                parse_and_store_health_from_file(
#                    user_id,
#                    file_path,
#                    websocket_manager,
#                    db,
#                )
#            )
#            # Small delay between files
#            time.sleep(0.1)
#
#        core_logger.print_to_log_and_console(
#            f"Bulk import completed: {total_files} files "
#            f"processed for user {user_id}"
#        )
#    finally:
#        db.close()