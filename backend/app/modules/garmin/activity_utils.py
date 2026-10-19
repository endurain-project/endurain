import os
import tempfile
from datetime import datetime

import garminconnect
from sqlalchemy.orm import Session

import core.async_bridge as core_async_bridge
import core.file_uploads as file_uploads
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.garmin.gear_utils as garmin_gear_utils
import modules.garmin.utils as garmin_utils
import modules.notifications.integration_service as notifications_integration
import modules.users.users_integrations.crud as user_integrations_crud
import modules.websocket.integration_service as websocket_integration
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


def _unlink_expired_account(user_id: int) -> None:
    """Unlink an account whose Garmin Connect token expired and tell the user.

    The notification row is written in the same short session as the unlink; the
    live push is handed to the main loop, since this runs on a worker thread.

    Args:
        user_id: The user whose account to unlink.
    """
    with SessionLocal() as db:
        user_integrations_crud.unlink_garminconnect_account(user_id, db)
        notification, ws_message = notifications_integration.create_garmin_token_expired_notification(user_id, db)
    core_async_bridge.dispatch(
        websocket_integration.push_to_user(user_id, {"message": ws_message, "notification_id": notification.id})
    )


def _download_and_ingest_activity(
    garminconnect_client: garminconnect.Garmin,
    activity: dict,
    user_id: int,
) -> list[activity_schema.ActivityRead]:
    """Download one Garmin activity, and ingest the files it contains.

    The downloads happen with no database session open. Everything is staged in a
    private temporary directory removed on the way out, so a failed or repeated
    sync can never be blocked by a file a previous attempt left behind.

    Args:
        garminconnect_client: A client authenticated as the user.
        activity: The Garmin activity summary.
        user_id: The user the activity belongs to.

    Returns:
        The activities stored from the downloaded files.
    """
    activity_id = activity["activityId"]
    activity_name = activity["activityName"]

    activity_gear = garminconnect_client.get_activity_gear(activity_id)
    zip_data = garminconnect_client.download_activity(
        activity_id,
        dl_fmt=garminconnect_client.ActivityDownloadFormat.ORIGINAL,
    )

    stored: list[activity_schema.ActivityRead] = []
    with tempfile.TemporaryDirectory(prefix="garmin-activity-") as work_dir:
        # Persisted through the unified pipeline so signature, size and filename
        # safety are enforced even on bytes that did not arrive via multipart upload.
        try:
            archive_path = file_uploads.save_validated_bytes_sync(
                zip_data,
                kind=file_uploads.UploadKind.ZIP,
                upload_dir=work_dir,
                filename=f"{int(activity_id)}.zip",
            )
        except Exception as err:
            logger.warning(
                f"User {user_id}: Garmin ZIP for activity {activity_id} failed validation: {type(err).__name__}",
                exc_info=err,
            )
            return stored

        # Zip-slip-safe extraction with per-entry caps; each extracted entry is
        # re-validated as an activity file and invalid entries are dropped.
        try:
            extracted_paths = file_uploads.extract_validated_zip_sync(
                archive_path,
                dest_dir=os.path.join(work_dir, "extracted"),
                per_entry_kind=file_uploads.UploadKind.ACTIVITY,
            )
        except Exception as err:
            logger.warning(
                f"User {user_id}: Garmin ZIP extraction failed for activity {activity_id}: {type(err).__name__}",
                exc_info=err,
            )
            return stored

        for full_file_path in extracted_paths:
            with SessionLocal() as db:
                parsed_result = activity_ingestion_integration.ingest_activity_file(
                    user_id=user_id,
                    file_path=str(full_file_path),
                    db=db,
                    source=activity_ingestion_integration.GarminSource(
                        # Resolved here rather than inside ingestion: which local gear
                        # a Garmin UUID maps to (and whether gear sync is even on) is
                        # this module's knowledge, not the pipeline's.
                        gear_id=garmin_gear_utils.resolve_synced_gear_id(user_id, activity_gear, db),
                        provider_gear_id=activity_gear[0]["uuid"] if activity_gear else None,
                        activity_name=activity_name,
                    ),
                )
            if parsed_result:
                stored.extend(parsed_result)
            else:
                logger.warning(
                    f"User {user_id}: Failed to parse Garmin activity {activity_id} file {full_file_path.name}"
                )
    return stored


def fetch_and_process_activities_by_dates(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch a user's Garmin Connect activities in a window and store the new ones.

    Runs on a worker thread. Garmin round trips run with no session open; the
    duplicate check and the store each open a short one. One activity failing is
    logged and skipped, so it does not stop the rest of the window.

    Args:
        garminconnect_client: A client authenticated as the user.
        start_date: Start of the window.
        end_date: End of the window.
        user_id: The user the activities belong to.

    Returns:
        The stored activities, or ``None`` when there were none.
    """
    try:
        garmin_activities = garminconnect_client.get_activities_by_date(
            str(start_date.date()),
            str(end_date.date()),
        )
    except garminconnect.GarminConnectAuthenticationError as err:
        logger.error(
            f"Garmin Connect token expired for user {user_id}. Unlinking account. User must re-link: {err}",
            exc_info=err,
        )
        _unlink_expired_account(user_id)
        return None
    except Exception as err:
        logger.error(
            f"Error fetching activities for user {user_id} between {start_date.date()} and {end_date.date()}: {err}",
            exc_info=err,
        )
        return None

    if garmin_activities is None:
        logger.info(
            f"User {user_id}: No new Garmin Connect activities found between {start_date.date()} and {end_date.date()}",
            extra=core_logger.context(console=True),
        )
        return None

    parsed_activities: list[activity_schema.ActivityRead] = []
    for activity in garmin_activities:
        activity_id = activity["activityId"]

        with SessionLocal() as db:
            already_stored = activity_integration.get_activity_by_garminconnect_id(activity_id, user_id, db)
        if already_stored:
            logger.info(f"User {user_id}: Activity {activity_id} already stored in the database")
            continue

        logger.info(f"User {user_id}: Processing activity {activity_id}")
        try:
            parsed_activities.extend(_download_and_ingest_activity(garminconnect_client, activity, user_id))
        except Exception as err:
            logger.error(
                f"User {user_id}: Error processing Garmin Connect activity {activity_id}: {err}",
                exc_info=err,
            )

    return parsed_activities if parsed_activities else None


def get_user_garminconnect_client(user_id: int, db: Session):
    try:
        # Get the user integrations by user ID
        user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(user_id, db)

        if user_integrations is None:
            logger.info(f"User {user_id}: Garmin Connect not linked")
            return None

        # Create a Garmin Connect client with the user's access token
        garminconnect_client = garmin_utils.login_garminconnect_using_tokens(
            user_integrations.garminconnect_token,
        )

        # return the Garmin Connect client
        return garminconnect_client
    except Exception as err:
        # Log specific errors during getting the Garmin Connect client
        logger.error(f"Error in get_user_garminconnect_client: {err}", exc_info=err)

        # Return None if the client cannot be created
        return None


def get_user_garminconnect_activities_by_dates(
    start_date: datetime,
    end_date: datetime,
    user_id: int,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch and store one user's Garmin Connect activities recorded in a window.

    Args:
        start_date: Start of the window.
        end_date: End of the window.
        user_id: The user to sync.

    Returns:
        The stored activities, or ``None`` when Garmin Connect is not linked or
        nothing new came back.
    """
    try:
        with SessionLocal() as db:
            garminconnect_client = get_user_garminconnect_client(user_id, db)

        if garminconnect_client is None:
            return None

        logger.info(
            f"User {user_id}: Started Garmin Connect activities processing for date range "
            f"{start_date.date()} to {end_date.date()}"
        )
        processed = fetch_and_process_activities_by_dates(garminconnect_client, start_date, end_date, user_id)
        logger.info(f"User {user_id}: {len(processed) if processed else 0} Garmin Connect activities processed")
        return processed
    except Exception as err:
        logger.error(f"Error in get_user_garminconnect_activities_by_dates: {err}", exc_info=err)
        return None
