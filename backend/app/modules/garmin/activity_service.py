"""Garmin Connect activity sync: fetch the window, download each file and hand it to ingestion."""

import os
import tempfile
from datetime import datetime

import garminconnect

import core.database as core_database
import core.exceptions as core_exceptions
import core.file_uploads as file_uploads
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.garmin.constants as garmin_constants
import modules.garmin.gear_service as garmin_gear_service
import modules.garmin.rate_limit_store as garmin_rate_limit_store
import modules.garmin.service as garmin_service

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
            with core_database.SessionLocal() as db:
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
            # Ingestion logs a file it could not store and answers None, so the window moves on.
            if parsed_result:
                stored.extend(parsed_result)
    return stored


def _process_listed_activity(
    session: garmin_service.GarminSession,
    activity: dict,
    user_id: int,
    rate_limits: garmin_rate_limit_store.GarminRateLimitStore,
) -> list[activity_schema.ActivityRead]:
    """Download and store one activity of a window, unless it is already stored.

    Args:
        session: The user's authenticated Garmin Connect session.
        activity: The Garmin activity summary.
        user_id: The user the activity belongs to.
        rate_limits: The shared Garmin Connect rate-limit state.

    Returns:
        The activities stored from it.

    Raises:
        WindowStoppedError: When Garmin Connect rejected the token, which has been dealt with: the account is
            unlinked, so no other activity of the window can be fetched.
        TooManyRequestsError: When Garmin Connect rate limits the account.
    """
    activity_id = activity["activityId"]

    with core_database.SessionLocal() as db:
        already_stored = activity_integration.get_activity_by_garminconnect_id(activity_id, user_id, db)
    if already_stored:
        logger.debug(
            "Activity already stored in the database",
            extra=core_logger.context(user_id=user_id, activity_id=activity_id),
        )
        return []

    logger.debug("Processing activity", extra=core_logger.context(user_id=user_id, activity_id=activity_id))
    try:
        return _download_and_ingest_activity(session.client, activity, user_id)
    except garminconnect.GarminConnectAuthenticationError as err:
        garmin_service.handle_rejected_token(user_id, session, err)
        raise activity_ingestion_integration.WindowStoppedError from err
    except garminconnect.GarminConnectTooManyRequestsError as err:
        # Ingestion skips what is already stored, so the deferred refresh resumes where this stopped.
        raise garmin_service.rate_limit_error(err, user_id, rate_limits) from err


def fetch_and_process_activities_by_dates(
    session: garmin_service.GarminSession,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    rate_limits: garmin_rate_limit_store.GarminRateLimitStore,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch a user's Garmin Connect activities in a window and store the new ones.

    Runs on a worker thread. Garmin round trips run with no session open; the
    duplicate check and the store each open a short one. An activity failing does
    not stop the rest of the window, but the first failure is raised once the
    window is done, so the refresh job fails and is retried, as for any provider. A file ingestion
    could not store is logged by ingestion and skipped, and does not fail the window.

    Args:
        session: The user's authenticated Garmin Connect session.
        start_date: Start of the window.
        end_date: End of the window.
        user_id: The user the activities belong to.
        rate_limits: The shared Garmin Connect rate-limit state.

    Returns:
        The stored activities, or ``None`` when there were none.

    Raises:
        TooManyRequestsError: When Garmin Connect rate limits the window; the refresh is deferred.
        Exception: The first failure of the window fetch or of an activity.
    """
    try:
        garmin_activities = session.client.get_activities_by_date(
            str(start_date.date()),
            str(end_date.date()),
        )
    except garminconnect.GarminConnectAuthenticationError as err:
        garmin_service.handle_rejected_token(user_id, session, err)
        return None
    except garminconnect.GarminConnectTooManyRequestsError as err:
        raise garmin_service.rate_limit_error(err, user_id, rate_limits) from err

    if garmin_activities is None:
        logger.debug(
            "No new Garmin Connect activities found",
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        return None

    stored = activity_ingestion_integration.run_provider_window(
        garmin_activities,
        lambda activity: _process_listed_activity(session, activity, user_id, rate_limits),
        provider=garmin_constants.PROVIDER_NAME,
        user_id=user_id,
        describe=lambda activity: {"activity_id": activity["activityId"]},
        propagate=(core_exceptions.TooManyRequestsError,),
    )
    parsed_activities = [parsed for activity_result in stored for parsed in activity_result]
    return parsed_activities if parsed_activities else None


def get_user_garminconnect_activities_by_dates(
    user_id: int,
    start_date: datetime,
    end_date: datetime,
    rate_limits: garmin_rate_limit_store.GarminRateLimitStore,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch and store one user's Garmin Connect activities recorded in a window.

    Args:
        user_id: The user to sync.
        start_date: Start of the window.
        end_date: End of the window.
        rate_limits: The shared Garmin Connect rate-limit state.

    Returns:
        The stored activities, or ``None`` when Garmin Connect is not linked or
        nothing new came back.

    Raises:
        TooManyRequestsError: When Garmin Connect rate limits the account.
        Exception: Whatever the sync raised, so the refresh job fails and is retried.
    """
    with garmin_service.linked_session(user_id, rate_limits) as session:
        if session is None:
            return None

        logger.info(
            "Started Garmin Connect activities processing for date range to",
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        processed = fetch_and_process_activities_by_dates(session, start_date, end_date, user_id, rate_limits)
        logger.info(
            "Garmin Connect activities processed",
            extra=core_logger.context(user_id=user_id, count=len(processed) if processed else 0),
        )
        return processed
