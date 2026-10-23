"""Garmin Connect activity sync: fetch the window, download each file and hand it to ingestion."""

import os
import tempfile
from datetime import datetime

import garminconnect

import core.file_uploads as file_uploads
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.garmin.gear_service as garmin_gear_service
import modules.garmin.service as garmin_service
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


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
                "Garmin ZIP for activity failed validation",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, activity_id=activity_id, error_type=type(err).__name__),
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
                "Garmin ZIP extraction failed for activity",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, activity_id=activity_id, error_type=type(err).__name__),
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
                        gear_id=garmin_gear_service.resolve_synced_gear_id(user_id, activity_gear, db),
                        provider_gear_id=activity_gear[0]["uuid"] if activity_gear else None,
                        activity_name=activity_name,
                    ),
                )
            if parsed_result:
                stored.extend(parsed_result)
            else:
                logger.warning(
                    "Failed to parse Garmin activity file",
                    extra=core_logger.context(user_id=user_id, activity_id=activity_id, file_name=full_file_path.name),
                )
    return stored


def fetch_and_process_activities_by_dates(
    session: garmin_service.GarminSession,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch a user's Garmin Connect activities in a window and store the new ones.

    Runs on a worker thread. Garmin round trips run with no session open; the
    duplicate check and the store each open a short one. One activity failing is
    logged and skipped, so it does not stop the rest of the window.

    Args:
        session: The user's authenticated Garmin Connect session.
        start_date: Start of the window.
        end_date: End of the window.
        user_id: The user the activities belong to.

    Returns:
        The stored activities, or ``None`` when there were none.
    """
    garminconnect_client = session.client
    try:
        garmin_activities = garminconnect_client.get_activities_by_date(
            str(start_date.date()),
            str(end_date.date()),
        )
    except garminconnect.GarminConnectAuthenticationError as err:
        garmin_service.handle_rejected_token(user_id, session, err)
        return None
    except Exception as err:
        logger.error(
            "Error fetching activities for user",
            exc_info=err,
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        return None

    if garmin_activities is None:
        logger.info(
            "No new Garmin Connect activities found",
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        return None

    parsed_activities: list[activity_schema.ActivityRead] = []
    for activity in garmin_activities:
        activity_id = activity["activityId"]

        with SessionLocal() as db:
            already_stored = activity_integration.get_activity_by_garminconnect_id(activity_id, user_id, db)
        if already_stored:
            logger.info(
                "Activity already stored in the database",
                extra=core_logger.context(user_id=user_id, activity_id=activity_id),
            )
            continue

        logger.info(
            "Processing activity",
            extra=core_logger.context(user_id=user_id, activity_id=activity_id),
        )
        try:
            parsed_activities.extend(_download_and_ingest_activity(garminconnect_client, activity, user_id))
        except garminconnect.GarminConnectAuthenticationError as err:
            garmin_service.handle_rejected_token(user_id, session, err)
            break
        except Exception as err:
            logger.error(
                "Error processing Garmin Connect activity",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, activity_id=activity_id),
            )

    return parsed_activities if parsed_activities else None


def get_user_garminconnect_activities_by_dates(
    user_id: int,
    start_date: datetime,
    end_date: datetime,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch and store one user's Garmin Connect activities recorded in a window.

    Args:
        user_id: The user to sync.
        start_date: Start of the window.
        end_date: End of the window.

    Returns:
        The stored activities, or ``None`` when Garmin Connect is not linked or
        nothing new came back.
    """
    session = None
    try:
        with SessionLocal() as db:
            session = garmin_service.get_user_garminconnect_session(user_id, db)

        if session is None:
            return None

        logger.info(
            "Started Garmin Connect activities processing for date range to",
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        processed = fetch_and_process_activities_by_dates(session, start_date, end_date, user_id)
        logger.info(
            "Garmin Connect activities processed",
            extra=core_logger.context(user_id=user_id, count=len(processed) if processed else 0),
        )
        return processed
    except Exception as err:
        logger.error(
            "Error in get_user_garminconnect_activities_by_dates",
            exc_info=err,
        )
        return None
    finally:
        if session is not None:
            garmin_service.save_refreshed_token(user_id, session)
