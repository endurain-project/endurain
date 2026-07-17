import asyncio
from datetime import UTC, datetime, timedelta

import garminconnect
from sqlalchemy.orm import Session

import core.config as core_config
import core.file_uploads as file_uploads
import core.logger as core_logger
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.orchestrator as ingestion_orchestrator
import modules.garmin.utils as garmin_utils
import modules.notifications.utils as notifications_utils
import modules.users.users.crud as users_crud
import modules.users.users_integrations.crud as user_integrations_crud
import modules.websocket.manager as websocket_manager
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
        # Run in a thread pool to avoid blocking the asyncio event loop with
        # the synchronous requests-based garminconnect library.
        garmin_activities = await asyncio.to_thread(
            garminconnect_client.get_activities_by_date,
            str(start_date.date()),
            str(end_date.date()),
        )
    except garminconnect.GarminConnectAuthenticationError as err:
        core_logger.print_to_log(
            f"Garmin Connect token expired for user {user_id}. Unlinking account. User must re-link: {err}",
            "error",
            exc=err,
        )
        user_integrations_crud.unlink_garminconnect_account(user_id, db)
        await notifications_utils.create_garmin_token_expired_notification(user_id, ws_manager)
        return None
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

    parsed_activities: list[activities_schema.Activity] = []

    # Download activities
    for activity in garmin_activities:
        # Get the activity ID
        activity_id = activity["activityId"]
        activity_name = activity["activityName"]

        # Check if the activity is already stored in the database
        activity_db = activities_crud.get_activity_by_garminconnect_id_from_user_id(activity_id, user_id, db)

        if activity_db:
            # Log an informational event if the activity is already stored
            core_logger.print_to_log(f"User {user_id}: Activity {activity_id} already stored in the database")
            continue

        core_logger.print_to_log(f"User {user_id}: Processing activity {activity_id}")

        # Get activity gear — offload to thread pool to avoid blocking event loop
        activity_gear = await asyncio.to_thread(garminconnect_client.get_activity_gear, activity_id)

        # Download the activity in original format (.zip file) — offload to thread pool
        zip_data = await asyncio.to_thread(
            garminconnect_client.download_activity,
            activity_id,
            dl_fmt=garminconnect_client.ActivityDownloadFormat.ORIGINAL,
        )

        # Persist the downloaded ZIP through the unified pipeline so
        # signature, size and filename safety are enforced even on
        # bytes that did not arrive via multipart upload.
        zip_filename = f"{int(activity_id)}.zip"
        try:
            output_file = await file_uploads.save_validated_bytes(
                zip_data,
                kind=file_uploads.UploadKind.ZIP,
                upload_dir=core_config.settings.FILES_DIR,
                filename=zip_filename,
            )
        except Exception as err:
            core_logger.print_to_log(
                f"User {user_id}: Garmin ZIP for activity {activity_id} failed validation: {type(err).__name__}",
                "warning",
                exc=err,
            )
            continue

        # Zip-slip-safe extraction with per-entry caps. Each
        # extracted entry is re-validated as an activity file and
        # invalid entries are dropped.
        try:
            extracted_paths = await file_uploads.extract_validated_zip(
                output_file,
                dest_dir=core_config.settings.FILES_DIR,
                per_entry_kind=file_uploads.UploadKind.ACTIVITY,
            )
        except Exception as err:
            # Include the HTTPException detail (error code + message)
            # when available; `type(err).__name__` alone collapses
            # every one of the nine failure modes in
            # `_extract_validated_zip_sync` to the single string
            # "HTTPException", making root-cause diagnosis impossible
            # without reproduction (#749).
            err_detail = getattr(err, "detail", None)
            core_logger.print_to_log(
                f"User {user_id}: Garmin ZIP extraction failed for activity {activity_id}: "
                f"{type(err).__name__}" + (f" - {err_detail}" if err_detail is not None else ""),
                "warning",
                exc=err,
            )
            file_uploads.safe_remove_within(output_file, base_dir=core_config.settings.FILES_DIR)
            continue

        file_uploads.safe_remove_within(output_file, base_dir=core_config.settings.FILES_DIR)

        for full_file_path in extracted_paths:
            parsed_result = await ingestion_orchestrator.parse_and_store_activity_from_file(
                token_user_id=user_id,
                file_path=str(full_file_path),
                db=db,
                from_garmin=True,
                garminconnect_gear=activity_gear,
                activity_name=activity_name,
            )
            if parsed_result:
                parsed_activities.extend(parsed_result)
            else:
                # parse_and_store_activity_from_file only moves the
                # extracted file out of dest_dir on success. On
                # failure (for non-bulk-import callers, which
                # includes this Garmin sync path) the file is left in
                # place, so the next sync cycle re-downloads the
                # activity and extraction fails with
                # ZIP_TARGET_EXISTS forever (#750). Clean it up here
                # so the activity can be retried.
                core_logger.print_to_log(
                    f"User {user_id}: Failed to parse Garmin activity {activity_id} file "
                    f"{full_file_path.name}; removing it to avoid a perpetual "
                    "ZIP_TARGET_EXISTS failure loop on the next sync",
                    "warning",
                )
                file_uploads.safe_remove_within(full_file_path, base_dir=core_config.settings.FILES_DIR)

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
            calculated_start_date = datetime.now(UTC) - timedelta(days=days)
            calculated_end_date = datetime.now(UTC)

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
        user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(user_id, db)

        if user_integrations is None:
            core_logger.print_to_log(f"User {user_id}: Garmin Connect not linked")
            return None

        # Create a Garmin Connect client with the user's access token
        garminconnect_client = garmin_utils.login_garminconnect_using_tokens(
            user_integrations.garminconnect_token,
        )

        # return the Garmin Connect client
        return garminconnect_client
    except Exception as err:
        # Log specific errors during getting the Garmin Connect client
        core_logger.print_to_log(f"Error in get_user_garminconnect_client: {err}", "error", exc=err)

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
            garminconnect_activities_processed = await fetch_and_process_activities_by_dates(
                garminconnect_client,
                start_date,
                end_date,
                user_id,
                ws_manager,
                db,
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
