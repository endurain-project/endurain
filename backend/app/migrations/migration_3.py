"""
Migration 3: back-fill laps, steps, and sets for all activities.

Processes every existing activity from FIT/GPX files or Strava and populates
the laps, workout steps, and sets tables.
"""

import asyncio
import glob
import os

import fitdecode
from sqlalchemy.orm import Session

import core.config as core_config
import core.file_uploads as file_uploads
import core.logger as core_logger
import migrations.crud as migrations_crud
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.crud as activities_crud
import modules.activities.activity_file_import.utils as activity_file_import_utils
import modules.activities.activity_file_import.utils_fit as fit_utils
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.garmin.activity_utils as garmin_activity_utils
import modules.strava.activity_utils as strava_activity_utils
import modules.strava.utils as strava_utils
from modules.activities.activity_exercise_titles import (
    crud as activity_exercise_titles_crud,
)

logger = core_logger.get_logger(__name__)


def process_migration_3(db: Session) -> None:
    """
    Run migration 3 for all existing activities.

    Args:
        db: Active database session.

    Returns:
        None.

    Raises:
        None — errors are logged; the migration flag is not
        set when any activity fails to process.
    """
    logger.info("Started migration 3", extra=core_logger.context(console=True))

    activities_processed_with_no_errors = True

    try:
        activities = activities_crud.get_all_activities_for_migration(db)
    except Exception as err:
        logger.error(
            f"Migration 3 - Error fetching activities: {err}", exc_info=err, extra=core_logger.context(console=True)
        )
        return

    if activities:
        for activity in activities:
            try:
                if activity.strava_activity_id is None:
                    # check if activity file exists
                    activity_fit_file_path = find_activity_fit_file(activity.id)
                    processed_dir = core_config.FILES_PROCESSED_DIR
                    activity_gpx_file_path = os.path.join(
                        processed_dir,
                        f"{activity.id}.gpx",
                    )

                    if (
                        activity_fit_file_path is None or not os.path.exists(activity_fit_file_path)
                    ) and activity.garminconnect_activity_id is not None:
                        get_fit_file_from_garminconnect(activity, db)
                        activity_fit_file_path = find_activity_fit_file(activity.id)

                    # if .gpx and .fit for activity do not exist, skip
                    if (
                        activity_fit_file_path is None or not os.path.exists(activity_fit_file_path)
                    ) and not os.path.exists(activity_gpx_file_path):
                        logger.info(
                            f"Migration 3 - Activity {activity.id}"
                            " does not have a file. Will process it"
                            " using activity streams.",
                            extra=core_logger.context(console=True),
                        )
                        # Process the activity using streams
                        process_activity_using_streams(
                            activity,
                            db,
                        )
                    # if exists, process it
                    else:
                        if activity_fit_file_path is not None and os.path.exists(activity_fit_file_path):
                            # Process the .fit file
                            process_fit_file(
                                activity,
                                activity_fit_file_path,
                                db,
                            )
                        else:
                            # Process the .gpx activity
                            process_activity_using_streams(
                                activity,
                                db,
                            )
                else:
                    if process_strava_activity(activity, db) is False:
                        continue
            except Exception as err:
                activities_processed_with_no_errors = False
                logger.error(
                    f"Migration 3 - Failed to process activity {activity.id}: {err}",
                    exc_info=err,
                    extra=core_logger.context(console=True),
                )

    # Mark migration as executed
    if activities_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(3, db)
        except Exception as err:
            logger.error(
                f"Migration 3 - Failed to set migration as executed: {err}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
            return
    else:
        logger.error(
            "Migration 3 failed to process all activities. Will try again later.",
            extra=core_logger.context(console=True),
        )

    logger.info("Finished migration 3", extra=core_logger.context(console=True))


def find_activity_fit_file(activity_id: int) -> str | None:
    """
    Find the FIT file path for a given activity ID.

    Args:
        activity_id: The activity's primary-key ID.

    Returns:
        Absolute path to the FIT file, or None if not found.

    Raises:
        None.
    """
    processed_dir = core_config.FILES_PROCESSED_DIR

    # Try single activity file first
    single_path = os.path.join(processed_dir, f"{activity_id}.fit")
    if os.path.exists(single_path):
        return single_path

    # Then search through multi-activity files
    for filepath in glob.glob(os.path.join(processed_dir, "*.fit")):
        filename = os.path.basename(filepath)
        name_without_ext = os.path.splitext(filename)[0]
        activity_ids = name_without_ext.split("_")

        if str(activity_id) in activity_ids:
            return filepath

    # If not found
    return None


def get_fit_file_from_garminconnect(
    activity: activities_contracts.ActivityMigrationRef,
    db: Session,
) -> str:
    """
    Download the FIT file for an activity from Garmin Connect.

    Args:
        activity: ORM Activity instance.
        db: Active database session.

    Returns:
        Expected path to the downloaded FIT file.

    Raises:
        OSError: If the downloaded ZIP file cannot be removed.
    """
    # Log getting file from Garmin Connect
    logger.info(
        f"Migration 3 - Activity {activity.id} does not have"
        " a file, but it is a Garmin Connect activity."
        " Will retrieve file from Garmin.",
        extra=core_logger.context(console=True),
    )

    # Get the user Garmin Connect client
    garminconnect_client = garmin_activity_utils.get_user_garminconnect_client(activity.user_id, db)

    if garminconnect_client is None:
        logger.error(
            f"Migration 3 - Could not get Garmin Connect client for activity {activity.id}.",
            extra=core_logger.context(console=True),
        )
        return os.path.join(core_config.FILES_PROCESSED_DIR, f"{activity.id}.fit")

    # Download the activity in original format (.zip file)
    zip_data = garminconnect_client.download_activity(
        activity.garminconnect_activity_id,
        dl_fmt=garminconnect_client.ActivityDownloadFormat.ORIGINAL,
    )

    # Persist + extract through the unified pipeline. Migrations are
    # synchronous, so we drive the async helpers via a single
    # ``asyncio.run`` over both calls — one event-loop setup per
    # archive instead of two.
    gc_id = str(activity.garminconnect_activity_id)
    zip_filename = f"{gc_id}.zip"
    files_dir = core_config.settings.FILES_DIR
    fallback_path = os.path.join(core_config.FILES_PROCESSED_DIR, f"{activity.id}.fit")

    async def _save_and_extract() -> tuple[str, list]:
        saved = await file_uploads.save_validated_bytes(
            zip_data,
            kind=file_uploads.UploadKind.ZIP,
            upload_dir=files_dir,
            filename=zip_filename,
        )
        try:
            paths = await file_uploads.extract_validated_zip(
                saved,
                dest_dir=files_dir,
                per_entry_kind=file_uploads.UploadKind.ACTIVITY,
            )
        except BaseException:
            file_uploads.safe_remove_within(saved, base_dir=files_dir)
            raise
        return saved, paths

    try:
        output_file, extracted_paths = asyncio.run(_save_and_extract())
    except Exception as err:
        logger.error(
            f"Migration 3 - Garmin ZIP handling failed for activity {activity.id}: {type(err).__name__}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        return fallback_path

    file_uploads.safe_remove_within(output_file, base_dir=files_dir)

    try:
        # Define the directory where the processed files will be stored
        processed_dir = core_config.FILES_PROCESSED_DIR

        for extracted_path in extracted_paths:
            file_extension = os.path.splitext(extracted_path.name)[1]

            # Define new file path with activity ID as filename
            new_file_name = f"{activity.id}{file_extension}"

            # Move the file to the processed directory
            file_uploads.move_within(
                extracted_path,
                processed_dir,
                filename=new_file_name,
                src_base_dir=files_dir,
            )
    except Exception as err:
        logger.error(
            f"Migration 3 - Failed to move activity {activity.id} file: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )

    # check if activity file exists
    return os.path.join(core_config.FILES_PROCESSED_DIR, f"{activity.id}.fit")


def process_fit_file(
    activity: activities_contracts.ActivityMigrationRef,
    activity_fit_file_path: str,
    db: Session,
) -> None:
    """
    Parse a FIT file and persist its data to the database.

    Args:
        activity: ORM Activity instance.
        activity_fit_file_path: Absolute path to the FIT file.
        db: Active database session.

    Returns:
        None.

    Raises:
        Exception: Re-raised after logging on parse failure.
    """
    # Array to store sessions
    sessions = []

    # Array to store laps
    laps = []

    # Array to store workout steps
    workout_steps = []

    # Array to store exercise titles
    exercises_titles = []

    # Array to store sets
    sets = []

    logger.info(
        f"Migration 3 - Activity {activity.id} has a fit file. Will process it.",
        extra=core_logger.context(console=True),
    )
    try:
        # Open the FIT file
        with open(activity_fit_file_path, "rb") as fit_file:
            fit_data = fitdecode.FitReader(fit_file)

            # Iterate over FIT messages
            for frame in fit_data:
                if isinstance(frame, fitdecode.FitDataMessage):
                    # Parse session data
                    if frame.name == "session":
                        sessions.append(fit_utils.parse_frame_session(frame))

                    # Parse lap data
                    if frame.name == "lap":
                        laps.append(fit_utils.parse_frame_lap(frame))

                    # Extract workout step data
                    if frame.name == "workout_step":
                        workout_steps.append(fit_utils.parse_frame_workout_step(frame))

                    # Extract exercise title data
                    if frame.name == "exercise_title":
                        exercises_titles.append(fit_utils.parse_frame_exercise_title(frame))

                    # Extract set data
                    if frame.name == "set":
                        sets.append(fit_utils.parse_frame_set(frame))
        # Store data in the database
        store_data_in_db(
            activity,
            sessions,
            laps,
            workout_steps,
            exercises_titles,
            sets,
            db,
        )
    except Exception as err:
        logger.error(
            f"Migration 3 - Failed to process activity {activity.id} file: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        raise err


def process_activity_using_streams(
    activity: activities_contracts.ActivityMigrationRef,
    db: Session,
) -> None:
    """
    Build laps from activity streams and persist to the database.

    Args:
        activity: ORM Activity instance.
        db: Active database session.

    Returns:
        None.

    Raises:
        Exception: Re-raised after logging on processing failure.
    """
    logger.info(
        f"Migration 3 - Activity {activity.id} has a gpx file. Will process it.",
        extra=core_logger.context(console=True),
    )

    try:
        streams = activity_streams_crud.get_activity_streams(activity.id, db)
        stream_map = {stream.stream_type: stream.stream_waypoints for stream in (streams or [])}

        laps = activity_file_import_utils.generate_activity_laps(
            stream_map.get(activity_streams_constants.STREAM_TYPE_MAP) or [],
            stream_map.get(activity_streams_constants.STREAM_TYPE_ELEVATION) or [],
            stream_map.get(activity_streams_constants.STREAM_TYPE_POWER) or [],
            stream_map.get(activity_streams_constants.STREAM_TYPE_HR) or [],
            stream_map.get(activity_streams_constants.STREAM_TYPE_CADENCE) or [],
            stream_map.get(activity_streams_constants.STREAM_TYPE_SPEED) or [],
        )

        store_data_in_db(activity, [], laps, [], [], [], db)
    except Exception as err:
        logger.error(
            f"Migration 3 - Failed to process activity {activity.id} file: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        raise


def process_strava_activity(
    activity: activities_contracts.ActivityMigrationRef,
    db: Session,
) -> bool:
    """
    Fetch Strava laps for an activity and persist to the database.

    Args:
        activity: ORM Activity instance.
        db: Active database session.

    Returns:
        True if processed successfully, False otherwise.

    Raises:
        None.
    """
    # Get the user integrations by user ID
    user_integrations = strava_utils.fetch_user_integrations_and_validate_token(activity.user_id, db)

    if user_integrations is None:
        logger.info(
            f"Migration 3 - User {activity.user_id} does not have a Strava account linked. Skipping.",
            extra=core_logger.context(console=True),
        )
        # Skip the activity if the user does not have a Strava account linked
        return False

    activity_streams = activity_streams_crud.get_activity_streams(activity.id, db)

    # Create a dictionary from stream_type to waypoints
    stream_map = {stream.stream_type: stream.stream_waypoints for stream in (activity_streams or [])}

    # Create flags for which streams are available
    is_heart_rate_set = activity_streams_constants.STREAM_TYPE_HR in stream_map
    is_power_set = activity_streams_constants.STREAM_TYPE_POWER in stream_map
    is_cadence_set = activity_streams_constants.STREAM_TYPE_CADENCE in stream_map
    is_elevation_set = activity_streams_constants.STREAM_TYPE_ELEVATION in stream_map
    is_velocity_set = activity_streams_constants.STREAM_TYPE_SPEED in stream_map
    is_pace_set = activity_streams_constants.STREAM_TYPE_PACE in stream_map
    is_lat_lon_set = (
        activity_streams_constants.STREAM_TYPE_MAP in stream_map
    )  # Or: detailedActivity.start_latlng is not None

    # Extract waypoints (empty list if not set)
    hr_waypoints = stream_map.get(activity_streams_constants.STREAM_TYPE_HR, [])
    power_waypoints = stream_map.get(activity_streams_constants.STREAM_TYPE_POWER, [])
    cad_waypoints = stream_map.get(activity_streams_constants.STREAM_TYPE_CADENCE, [])
    ele_waypoints = stream_map.get(activity_streams_constants.STREAM_TYPE_ELEVATION, [])
    vel_waypoints = stream_map.get(activity_streams_constants.STREAM_TYPE_SPEED, [])
    pace_waypoints = stream_map.get(activity_streams_constants.STREAM_TYPE_PACE, [])
    lat_lon_waypoints = stream_map.get(activity_streams_constants.STREAM_TYPE_MAP, [])

    # Assemble final stream data list
    stream_data = [
        (is_heart_rate_set, activity_streams_constants.STREAM_TYPE_HR, hr_waypoints),
        (is_power_set, activity_streams_constants.STREAM_TYPE_POWER, power_waypoints),
        (is_cadence_set, activity_streams_constants.STREAM_TYPE_CADENCE, cad_waypoints),
        (is_elevation_set, activity_streams_constants.STREAM_TYPE_ELEVATION, ele_waypoints),
        (is_velocity_set, activity_streams_constants.STREAM_TYPE_SPEED, vel_waypoints),
        (is_pace_set, activity_streams_constants.STREAM_TYPE_PACE, pace_waypoints),
        (is_lat_lon_set, activity_streams_constants.STREAM_TYPE_MAP, lat_lon_waypoints),
    ]

    # Create a Strava client with the user's access token
    strava_client = strava_utils.create_strava_client(user_integrations)

    if not activity.strava_activity_id:
        logger.info(
            f"Migration 3 - Activity {activity.id} does not have a Strava activity ID. Skipping.",
            extra=core_logger.context(console=True),
        )
        return False

    # Get laps from Strava
    laps = strava_activity_utils.fetch_and_process_activity_laps(
        strava_client,
        activity.strava_activity_id,
        activity.user_id,
        stream_data,
    )

    # Create activity laps in the database
    activity_laps_crud.create_activity_laps(laps or [], activity.id, db)

    logger.info(f"Migration 3 - Strava activity {activity.id} file processed.", extra=core_logger.context(console=True))

    # Return true if the activity was processed successfully
    return True


def store_data_in_db(
    activity: activities_contracts.ActivityMigrationRef,
    sessions: list,
    laps: list,
    workout_steps: list,
    exercises_titles: list,
    sets: list,
    db: Session,
) -> None:
    """
    Persist FIT-file data (laps, steps, sets) to the database.

    Args:
        activity: ORM Activity instance.
        sessions: Parsed session records from the FIT file.
        laps: Parsed lap records from the FIT file.
        workout_steps: Parsed workout-step records.
        exercises_titles: Parsed exercise-title records.
        sets: Parsed set records from the FIT file.
        db: Active database session.

    Returns:
        None.

    Raises:
        None.
    """
    laps_to_store = []
    workout_steps_to_store = workout_steps if workout_steps else []
    exercises_titles_to_store = exercises_titles if exercises_titles else []
    sets_to_store = sets if sets else []

    if sessions and len(sessions) > 1:
        if laps:
            filtered_laps = []  # Temporary list to store filtered laps
            for lap in laps:
                start_time = activity.start_time
                end_time = activity.end_time
                lap_start_time = lap["start_time"]

                if start_time <= lap_start_time <= end_time:
                    # Append the lap to the temporary list
                    logger.info(
                        f"start_time: {start_time}, lap_start_time: {lap_start_time}, end_time: {end_time}",
                        extra=core_logger.context(console=True),
                    )
                    filtered_laps.append(lap)

            # Extend laps_to_store with the filtered laps
            laps_to_store.extend(filtered_laps)
    else:
        laps_to_store = laps if laps else []

    # Create activity laps in the database
    if laps_to_store:
        activity_laps_crud.create_activity_laps(laps_to_store, activity.id, db)

    # Create activity workout steps in the database
    if workout_steps_to_store:
        activity_workout_steps_crud.create_activity_workout_steps(workout_steps_to_store, activity.id, db)

    # Create activity exercise titles in the database
    if exercises_titles_to_store:
        activity_exercise_titles_crud.create_activity_exercise_titles(exercises_titles_to_store, db)

    # Create activity sets in the database
    if sets_to_store:
        activity_sets_crud.create_activity_sets(sets_to_store, activity.id, db)

    logger.info(f"Migration 3 - Activity {activity.id} processed.", extra=core_logger.context(console=True))
