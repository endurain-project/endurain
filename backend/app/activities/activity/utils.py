"""Activity import, parsing and aggregation utilities."""

import asyncio
import contextlib
import functools
import gzip
import os
import shutil
import statistics
import time
import uuid
from datetime import datetime
from pathlib import Path
from statistics import mean
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode

import requests
from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from geopy.distance import geodesic
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import activities.activity.crud as activities_crud
import activities.activity.models as activities_models
import activities.activity.schema as activities_schema
import activities.activity.thumbnail as activities_thumbnail
import activities.activity_file_import.utils_fit as fit_utils
import activities.activity_file_import.utils_gpx as gpx_utils
import activities.activity_file_import.utils_tcx as tcx_utils
import activities.activity_laps.crud as activity_laps_crud
import activities.activity_sets.crud as activity_sets_crud
import activities.activity_streams.constants as activity_streams_constants
import activities.activity_streams.crud as activity_streams_crud
import activities.activity_streams.models as activity_streams_models
import activities.activity_streams.schema as activity_streams_schema
import activities.activity_workout_steps.crud as activity_workout_steps_crud
import core.config as core_config
import core.cryptography as core_cryptography
import core.database as core_database
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import core.sanitization as core_sanitization
import core.timezone as core_timezone
import server_settings.crud as server_settings_crud
import strava.bulk_import_utils as strava_bulk_import_utils
import users.users.crud as users_crud
import users.users_privacy_settings.crud as users_privacy_settings_crud
import users.users_privacy_settings.models as users_privacy_settings_models
import websocket.manager as websocket_manager

# Global Activity Type Mappings (ID to Name)
ACTIVITY_ID_TO_NAME = {
    1: "Run",
    2: "Trail run",
    3: "Virtual run",
    4: "Ride",
    5: "Gravel ride",
    6: "MTB ride",
    7: "Virtual ride",
    8: "Lap swimming",
    9: "Open water swimming",
    10: "Workout",
    11: "Walk",
    12: "Hike",
    13: "Rowing",
    14: "Yoga",
    15: "Alpine ski",
    16: "Nordic ski",
    17: "Snowboard",
    18: "Transition",
    19: "Strength training",
    20: "Crossfit",
    21: "Tennis",
    22: "TableTennis",
    23: "Badminton",
    24: "Squash",
    25: "Racquetball",
    26: "Pickleball",
    27: "Commuting ride",
    28: "Indoor ride",
    29: "Mixed surface ride",
    30: "Windsurf",
    31: "Indoor walking",
    32: "Stand up paddling",
    33: "Surf",
    34: "Track run",
    35: "E-Bike ride",
    36: "E-Mountain Bike ride",
    37: "Ice Skate",
    38: "Soccer",
    39: "Padel",
    40: "Treadmill",
    41: "Cardio training",
    42: "Kayaking",
    43: "Sailing",
    44: "Snow shoeing",
    45: "Inline skating",
    46: "HIIT",
    47: "Jump rope",
    # Add other mappings as needed based on the full list in define_activity_type comments if required
    # "AlpineSki",
    # "BackcountrySki",
    # "Badminton",
    # "Canoeing",
    # "Crossfit",
    # "EBikeRide",
    # "Elliptical",
    # "EMountainBikeRide",
    # "Golf",
    # "GravelRide",
    # "Handcycle",
    # "HighIntensityIntervalTraining",
    # "Hike",
    # "IceSkate",
    # "InlineSkate",
    # "Kayaking",
    # "Kitesurf",
    # "MountainBikeRide",
    # "NordicSki",
    # "Pickleball",
    # "Pilates",
    # "Racquetball",
    # "Ride",
    # "RockClimbing",
    # "RollerSki",
    # "Rowing",
    # "Run",
    # "Sail",
    # "Skateboard",
    # "Snowboard",
    # "Snowshoe",
    # "Soccer",
    # "Squash",
    # "StairStepper",
    # "StandUpPaddling",
    # "Surfing",
    # "Swim",
    # "TableTennis",
    # "Tennis",
    # "TrailRun",
    # "Velomobile",
    # "VirtualRide",
    # "VirtualRow",
    # "VirtualRun",
    # "Walk",
    # "WeightTraining",
    # "Wheelchair",
    # "Windsurf",
    # "Workout",
    # "Yoga"
}

# Global Activity Type Mappings (Name to ID) - Case Insensitive Keys
ACTIVITY_NAME_TO_ID = {name.lower(): activity_type_id for activity_type_id, name in ACTIVITY_ID_TO_NAME.items()}
# Add specific variations found in define_activity_type
ACTIVITY_NAME_TO_ID.update(
    {
        "running": 1,
        "trail running": 2,
        "trailrun": 2,
        "trail": 2,
        "virtualrun": 3,
        "cycling": 4,
        "biking": 4,
        "road": 4,
        "gravelride": 5,
        "gravel_cycling": 5,
        "mountainbikeride": 6,
        "mountain": 6,
        "virtualride": 7,
        "virtual_ride": 7,
        "swim": 8,
        "swimming": 8,
        "lap_swimming": 8,
        "open_water_swimming": 9,
        "open_water": 9,
        "walk": 11,
        "walking": 11,
        "hike": 12,
        "hiking": 12,
        "rowing": 13,
        "indoor_rowing": 13,
        "yoga": 14,
        "alpineski": 15,
        "resort_skiing": 15,
        "alpine_skiing": 15,
        "nordicski": 16,
        "snowboard": 17,
        "transition": 18,
        "strength_training": 19,
        "weighttraining": 19,
        "crossfit": 20,
        "tennis": 21,
        "tabletennis": 22,
        "badminton": 23,
        "squash": 24,
        "racquetball": 25,
        "pickleball": 26,
        "commuting_ride": 27,
        "indoor_ride": 28,
        "indoor_cycling": 28,
        "mixed_surface_ride": 29,
        "windsurf": 30,
        "windsurfing": 30,
        "indoor_walking": 31,
        "stand_up_paddleboarding": 32,
        "standuppaddling": 32,
        "surfing": 33,
        "track running": 34,
        "trackrun": 34,
        "track": 34,
        "ebikeride": 35,
        "e_bike": 35,
        "ebike": 35,
        "e_bike_ride": 35,
        "e_bike_fitness": 35,
        "emountainbikeride": 36,
        "e_bike_mountain": 36,
        "ebikemountain": 36,
        "e_bike_mountain_ride": 36,
        "ebikemountainride": 36,
        "iceskate": 37,
        "soccer": 38,
        "padel": 39,
        "padelball": 39,
        "paddelball": 39,
        "treadmill": 40,
        "indoor_running": 40,
        "cardio_training": 41,
        "kayaking": 42,
        "sailing": 43,
        "sail": 43,
        "snowshoeing": 44,
        "snowshoe": 44,
        "inline_skating": 45,
        "inlineskate": 45,
        "hiit": 46,
        "high_intensity_interval_training": 46,
        "highintensityintervaltraining": 46,
        "jump_rope": 47,
        "jumprope": 47,
    }
)


def transform_schema_activity_to_model_activity(
    activity: activities_schema.Activity,
) -> activities_models.Activity:
    # Use an explicit UTC-aware created_at when provided,
    # otherwise let the database stamp the row with now().
    created_date = core_timezone.to_utc_aware(activity.created_at) if activity.created_at is not None else func.now()

    # Sanitize markdown fields to prevent XSS
    sanitized_description = core_sanitization.sanitize_markdown(activity.description)
    sanitized_private_notes = core_sanitization.sanitize_markdown(activity.private_notes)

    # Create a new activity object
    new_activity = activities_models.Activity(
        user_id=activity.user_id,
        description=sanitized_description,
        private_notes=sanitized_private_notes,
        distance=activity.distance,
        name=activity.name,
        activity_type=activity.activity_type,
        start_time=core_timezone.to_utc_aware(activity.start_time),
        end_time=core_timezone.to_utc_aware(activity.end_time),
        timezone=activity.timezone,
        total_elapsed_time=activity.total_elapsed_time,
        total_timer_time=(
            activity.total_timer_time if activity.total_timer_time is not None else activity.total_elapsed_time
        ),
        city=activity.city,
        town=activity.town,
        country=activity.country,
        created_at=created_date,
        elevation_gain=activity.elevation_gain,
        elevation_loss=activity.elevation_loss,
        pace=activity.pace,
        average_speed=activity.average_speed,
        max_speed=activity.max_speed,
        average_power=activity.average_power,
        max_power=activity.max_power,
        normalized_power=activity.normalized_power,
        average_hr=activity.average_hr,
        max_hr=activity.max_hr,
        average_cad=activity.average_cad,
        max_cad=activity.max_cad,
        workout_feeling=activity.workout_feeling,
        workout_rpe=activity.workout_rpe,
        calories=activity.calories,
        visibility=activity.visibility,
        gear_id=activity.gear_id,
        strava_gear_id=activity.strava_gear_id,
        strava_activity_id=activity.strava_activity_id,
        garminconnect_activity_id=activity.garminconnect_activity_id,
        garminconnect_gear_id=activity.garminconnect_gear_id,
        import_info=activity.import_info,
        is_hidden=activity.is_hidden if activity.is_hidden is not None else False,
        hide_start_time=activity.hide_start_time,
        hide_location=activity.hide_location,
        hide_map=activity.hide_map,
        hide_hr=activity.hide_hr,
        hide_power=activity.hide_power,
        hide_cadence=activity.hide_cadence,
        hide_elevation=activity.hide_elevation,
        hide_speed=activity.hide_speed,
        hide_pace=activity.hide_pace,
        hide_laps=activity.hide_laps,
        hide_workout_sets_steps=activity.hide_workout_sets_steps,
        hide_gear=activity.hide_gear,
        tracker_manufacturer=activity.tracker_manufacturer,
        tracker_model=activity.tracker_model,
        total_cycles=activity.total_cycles,
    )

    return new_activity


def serialize_activity(
    activity: activities_models.Activity,
) -> activities_schema.Activity:
    """
    Convert an ORM Activity to a schema with TZ.

    Converts ORM model to Pydantic schema and
    applies timezone formatting to datetime fields.
    Does NOT mutate the ORM object.

    Args:
        activity: The ORM Activity instance.

    Returns:
        An Activity schema with formatted datetimes.
    """
    schema = activities_schema.Activity.model_validate(activity)

    tz_name = activity.timezone
    schema.start_time_tz_applied = core_timezone.format_aware_datetime(activity.start_time, tz_name)
    schema.end_time_tz_applied = core_timezone.format_aware_datetime(activity.end_time, tz_name)
    schema.created_at_tz_applied = core_timezone.format_aware_datetime(activity.created_at, tz_name)

    schema.start_time = core_timezone.format_aware_datetime(activity.start_time, None)
    schema.end_time = core_timezone.format_aware_datetime(activity.end_time, None)
    schema.created_at = core_timezone.format_aware_datetime(activity.created_at, None)

    return schema


def apply_visibility_mask(
    schema: activities_schema.Activity,
    *,
    is_owner: bool,
    mask_private_notes: bool = True,
) -> activities_schema.Activity:
    """Mask hidden activity fields for non-owners.

    Mutates and returns the provided Pydantic schema instance.
    For owners no masking is applied.

    Args:
        schema: Activity schema to potentially mask.
        is_owner: Whether the requesting user owns the
            activity.
        mask_private_notes: Whether to clear private_notes
            for non-owners. Defaults to True.

    Returns:
        The (possibly mutated) Activity schema.
    """
    if is_owner:
        return schema
    if mask_private_notes:
        schema.private_notes = None
    if schema.hide_start_time:
        schema.start_time = None
        schema.end_time = None
    if schema.hide_location:
        schema.city = None
        schema.town = None
        schema.country = None
    if schema.hide_gear:
        schema.gear_id = None
        schema.strava_gear_id = None
        schema.garminconnect_gear_id = None
    return schema


def escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards in a user-provided term.

    Escapes ``\\``, ``%`` and ``_`` so they are matched
    literally. Use together with ``.like(..., escape="\\\\")``.

    Args:
        term: Raw search term.

    Returns:
        Escaped search term safe for use inside a ``LIKE``
        pattern.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def handle_gzipped_file(
    file_path: str,
) -> tuple[str, str]:
    """Handle gzipped files with bounded extraction.

    Args:
        file_path: Path to the gzipped activity file.

    Returns:
        Tuple containing the temporary file path and inner
        extension.

    Raises:
        HTTPException: 400 for invalid gzip content or 413 when
            decompressed content exceeds the configured limit.
    """
    path = Path(file_path)

    inner_filename = path.stem  # eg "activity_1234567890.fit"
    inner_file_extension = Path(inner_filename).suffix  # eg ".gz"
    temp_file_path: str | None = None
    bytes_written = 0

    try:
        with (
            gzip.open(path, "rb") as gzipped_file,
            NamedTemporaryFile(
                suffix=inner_file_extension,
                delete=False,
            ) as temp_file,
        ):
            temp_file_path = temp_file.name
            while True:
                chunk = gzipped_file.read(_DECOMPRESS_CHUNK_BYTES)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > _MAX_DECOMPRESSED_ACTIVITY_BYTES:
                    temp_file.close()
                    with contextlib.suppress(OSError):
                        os.remove(temp_file_path)
                    raise HTTPException(
                        status_code=(status.HTTP_413_CONTENT_TOO_LARGE),
                        detail=("Decompressed file exceeds maximum allowed size"),
                    )
                temp_file.write(chunk)
            temp_file.flush()

        core_logger.print_to_log_and_console(
            f"Decompressed {path} with inner type {inner_file_extension} to {temp_file_path}"
        )

        move_file(core_config.FILES_PROCESSED_DIR, path.name, str(path))

        return temp_file_path, inner_file_extension
    except HTTPException:
        raise
    except (OSError, EOFError, gzip.BadGzipFile) as err:
        if temp_file_path is not None:
            with contextlib.suppress(OSError):
                os.remove(temp_file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid gzip file",
        ) from err


def _prepare_bulk_import_activity(
    activity: activities_models.Activity,
    is_bulk_import: bool,
    created_activities_objects: list,
    strava_activities: dict | None,
    activity_metadata_dict: dict,
) -> activities_models.Activity | None:
    """Process a single activity for bulk import.

    Returns the (possibly updated) activity, or None if the activity
    should be skipped (e.g. duplicate from a multi-activity .fit file).

    When not a bulk import, returns the activity unchanged.
    """
    if not is_bulk_import:
        return activity

    # For a Strava bulk import of a multi-activity .fit file, check to see
    # if this is the same activity referenced in the activities.csv for
    # this file.
    if (
        len(created_activities_objects) > 1
        and strava_activities
        and activity_metadata_dict["metadata_found_in_csv"] is True
        and not strava_bulk_import_utils.does_activity_start_time_match_the_data_in_strava_activities_csv(
            activity, activity_metadata_dict
        )
    ):
        # This activity does not match the Strava CSV entry — skip import.
        core_logger.print_to_log_and_console(
            "Bulk activity import of multi-activity .fit file: "
            "skipping likely duplicate import. "
            "Start time does not align with start time for this .fit file "
            "in the Strava activities.csv file.",
            "debug",
        )
        return None

    # Add import metadata and Strava activities.csv metadata
    activity = strava_bulk_import_utils.append_bulk_import_metadata_to_activity(activity, activity_metadata_dict)
    return activity


async def parse_and_store_activity_from_file(
    token_user_id: int,
    file_path: str,
    websocket_manager: websocket_manager.WebSocketManager,
    db: Session,
    from_garmin: bool = False,
    is_bulk_import: bool = False,
    garminconnect_gear: dict | None = None,
    strava_activities: dict | None = None,
    import_initiated_time: str | None = None,
    users_existing_gear_nickname_to_id: dict | None = None,
    activity_name: str | None = None,
):
    """
    Parse an activity file and persist the result to the database.

    Supports .gpx, .tcx, .fit, and .gz files. Handles Garmin Connect and Strava
    bulk imports, moves processed files to the appropriate directory, and emits
    WebSocket notifications.

    Args:
        token_user_id: ID of the authenticated user performing the import.
        file_path: Absolute path to the activity file to parse.
        websocket_manager: Manager used to push real-time notifications to
            connected clients.
        db: SQLAlchemy database session.
        from_garmin: Whether the file originates from a Garmin Connect sync.
        garminconnect_gear: Garmin Connect gear metadata to associate with the
            activity.
        strava_activities: Strava bulk-import metadata dict keyed by filename,
            then by activities.csv column header.
        import_initiated_time: ISO timestamp of when the bulk import was
            initiated.
        users_existing_gear_nickname_to_id: Mapping of gear nickname to
            internal gear ID, used during Strava bulk imports.
        activity_name: Optional override for the activity name.

    Returns:
        List of created activity schema objects, or None if the file could not
            be parsed.

    Raises:
        HTTPException: When the user is not found.
    """
    try:
        # Get file extension
        _, file_extension = os.path.splitext(file_path)
        file_extension = file_extension.lower()

        if file_extension not in core_config.SUPPORTED_FILE_FORMATS:
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail=("File extension not supported. Supported file extensions are .gpx, .fit, .tcx and .gz"),
            )

        # Defense-in-depth signature check on files queued for
        # processing (Garmin / Strava import paths).
        await core_file_uploads.validate_local_file(
            file_path,
            kind=(
                core_file_uploads.UploadKind.GZIP if file_extension == ".gz" else core_file_uploads.UploadKind.ACTIVITY
            ),
        )

        # Get pathless file name with extension, as this is the dictionary key for Strava's bulk import activities dictionary.
        _, file_base_name = os.path.split(file_path)

        garmin_connect_activity_id = None

        if from_garmin:
            garmin_connect_activity_id = os.path.basename(file_path).split("_")[0]

        if file_extension == ".gz":
            file_path, file_extension = handle_gzipped_file(file_path)
            file_extension = file_extension.lower()
            if file_extension not in core_config.SUPPORTED_FILE_FORMATS or file_extension == ".gz":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=("Decompressed file extension is not supported"),
                )
            await core_file_uploads.validate_local_file(
                file_path,
                kind=core_file_uploads.UploadKind.ACTIVITY,
            )

        # Open the file and process it
        with open(file_path, "rb"):
            user = users_crud.get_user_by_id(token_user_id, db)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

            user_privacy_settings = users_privacy_settings_crud.get_user_privacy_settings_by_user_id(user.id, db)
            if user_privacy_settings is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User privacy settings not found",
                )

            # Parse the file in a thread pool to avoid
            # blocking the event loop with CPU-bound and
            # sync I/O work (gpxpy, geopy, timezonefinder)
            parsed_info = await run_in_threadpool(
                functools.partial(
                    parse_file,
                    token_user_id,
                    user_privacy_settings,
                    file_extension,
                    file_path,
                    db,
                    activity_name,
                )
            )

            # Gather supplemental metadata. Check if a Strava bulk import is in
            # progress, and if so check to see if any additional information
            # can be added to the activity.
            activity_metadata_dict = {}
            if strava_activities and isinstance(strava_activities, dict) and import_initiated_time and is_bulk_import:
                # Build a metadata dict (which will also include an
                # import_dict) based on information in the strava_activities
                # dict.
                activity_metadata_dict = strava_bulk_import_utils.build_metadata_dict(
                    file_base_name,
                    strava_activities,
                    import_initiated_time,
                    users_existing_gear_nickname_to_id,
                )
            elif import_initiated_time and is_bulk_import:
                # Not doing a Strava bulk import, so build an import info dict
                # that reflects the generic import.
                import_dict = strava_bulk_import_utils.build_import_dictionary(
                    file_base_name, import_initiated_time, False
                )
                activity_metadata_dict["import_dict"] = import_dict

            # Work through the parsed info; process and store any activity
            # information found (specific routines depend on file type
            # .gpx/.tcx and .fit have very different needs)
            if parsed_info is not None:
                created_activities = []
                ids_to_filename = ""
                if file_extension.lower() in (
                    ".gpx",
                    ".tcx",
                ):
                    # Add import metadata and Strava activities.csv metadata to parsed_info
                    if is_bulk_import:
                        parsed_info = strava_bulk_import_utils.append_bulk_import_metadata_to_activity(
                            parsed_info, activity_metadata_dict
                        )

                    # Store the activity in the database
                    created_activity = await store_activity(parsed_info, websocket_manager, db)
                    created_activities.append(created_activity)
                    ids_to_filename += str(created_activity.id)
                elif file_extension.lower() == ".fit":
                    # Split the records by activity (check for multiple activities in the file)
                    split_records_by_activity = fit_utils.split_records_by_activity(parsed_info)

                    # Create activity objects for each activity in the file
                    if from_garmin:
                        created_activities_objects = fit_utils.create_activity_objects(
                            split_records_by_activity,
                            token_user_id,
                            user_privacy_settings,
                            (int(garmin_connect_activity_id) if garmin_connect_activity_id else None),
                            garminconnect_gear if garminconnect_gear else None,
                            db,
                        )
                    else:
                        created_activities_objects = fit_utils.create_activity_objects(
                            split_records_by_activity,
                            token_user_id,
                            user_privacy_settings,
                            None,
                            None,
                            db,
                        )

                    for activity in created_activities_objects:
                        activity = _prepare_bulk_import_activity(
                            activity,
                            is_bulk_import,
                            created_activities_objects,
                            strava_activities,
                            activity_metadata_dict,
                        )
                        if activity is None:
                            continue

                        # Store the activity in the database
                        created_activity = await store_activity(activity, websocket_manager, db)

                        created_activities.append(created_activity)

                    ids_to_filename = "_".join(str(activity.id) for activity in created_activities)
                else:
                    # Should no longer get here due to screening of extensions
                    # in router.py, but why not.
                    core_logger.print_to_log_and_console(f"File extension not supported: {file_extension}", "error")

                # Define the directory where the processed files will be stored
                processed_dir = core_config.FILES_PROCESSED_DIR

                # Define new file path with activity ID as filename
                new_file_name = f"{ids_to_filename}{file_extension}"

                # Move the file to the processed directory
                move_file(processed_dir, new_file_name, file_path)

                # Log file move, import any associated media, and log completion.
                if is_bulk_import:
                    core_logger.print_to_log_and_console(
                        f"Bulk file import: File successfully processed and moved. {file_path} - has become {new_file_name}"
                    )

                    # Deal with Strava bulk import media.
                    # Note - even multi-activity .fit files are good with this code, as there should only be a single imported activity per file in the Strava activities file directory.
                    if strava_activities:
                        await strava_bulk_import_utils.import_media_from_strava_bulk_export(
                            strava_activities,
                            created_activity,
                            file_base_name,
                            db,
                        )

                    core_logger.print_to_log_and_console(
                        f"Bulk file import: Import work complete for file {file_base_name}."
                    )

                # Return the created activity
                return created_activities
            else:
                return None
    except (
        HTTPException,
        OSError,
        EOFError,
        gzip.BadGzipFile,
        shutil.Error,
        SQLAlchemyError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
    ) as err:
        if is_bulk_import:
            # Log the exception
            core_logger.print_to_log_and_console(
                f"Bulk file import: Error while parsing {file_path} in parse_and_store_activity_from_file - {err!s}",
                "error",
                exc=err,
            )
            try:
                # Move the exception-causing file to an import errors directory.
                if strava_activities:
                    # Use Strava bulk import errors directory if we are doing a Strava bulk import
                    error_file_dir = core_config.STRAVA_BULK_IMPORT_IMPORT_ERRORS_DIR
                else:
                    # otherwise use standard bulk import error directory
                    error_file_dir = core_config.FILES_BULK_IMPORT_IMPORT_ERRORS_DIR
                os.makedirs(error_file_dir, exist_ok=True)
                move_file(error_file_dir, os.path.basename(file_path), file_path)
                core_logger.print_to_log_and_console(
                    f"Bulk file import: Due to import error, file {file_path} has been moved to {error_file_dir}",
                    "error",
                )
            except OSError:
                core_logger.print_to_log_and_console(
                    f"Bulk file import: Failed to move the error-producing file {file_path} to the import-error directory.",
                    "error",
                )
        core_logger.print_to_log_and_console(
            f"Error in parse_and_store_activity_from_file - {err}",
            "error",
            exc=err,
        )
        # Background-task callers expect ``None`` on failure rather
        # than re-raising; make that contract explicit.
        return None


# Maximum size accepted when decompressing a gzipped activity
# upload. Mirrors core_file_uploads' activity cap; safeuploads
# enforces the same limit on the wrapping ``.gz`` upload before we
# get here, but we re-cap defensively while expanding the inner
# payload (decompression-bomb defense in depth).
_MAX_DECOMPRESSED_ACTIVITY_BYTES = 200 * 1024 * 1024
# Chunk size used while streaming decompressed bytes to disk.
_DECOMPRESS_CHUNK_BYTES = 1024 * 1024


def _cleanup_upload_artifacts(file_paths: list[str]) -> None:
    """Remove files created during failed activity uploads.

    Args:
        file_paths: Files to remove if they still exist.

    Returns:
        None.

    Raises:
        None.
    """
    for file_path in file_paths:
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except OSError as err:
            core_logger.print_to_log(
                f"Failed to cleanup upload artifact {file_path}: {err}",
                "warning",
                exc=err,
            )


async def parse_and_store_activity_from_uploaded_file(
    token_user_id: int,
    file: UploadFile,
    websocket_manager: websocket_manager.WebSocketManager,
    db: Session,
):
    """Persist an uploaded activity file and return the result.

    Validates the filename and extension, streams the upload to
    disk in a thread pool, and delegates parsing to ``parse_file``.

    Args:
        token_user_id: Authenticated user ID.
        file: Incoming FastAPI UploadFile.
        websocket_manager: Manager used for notifications.
        db: Database session.

    Returns:
        List of created Activity schemas, or None if no activity
        could be parsed from the file.

    Raises:
        HTTPException: 400/404/406/413 on validation errors,
            500 on internal failures.
    """
    # Validate filename exists
    if file.filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Pre-check the extension so we can short-circuit with a
    # human-friendly 406 before invoking the validator (which would
    # otherwise raise a generic ExtensionSecurityError -> 400).
    _, file_extension = os.path.splitext(file.filename)
    if file_extension.lower() not in core_config.SUPPORTED_FILE_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=("File extension not supported. Supported file extensions are .gpx, .fit, .tcx and .gz"),
        )

    upload_dir = core_config.settings.FILES_DIR
    upload_kind = (
        core_file_uploads.UploadKind.GZIP if file_extension.lower() == ".gz" else core_file_uploads.UploadKind.ACTIVITY
    )
    # Server-generated filename to defeat path traversal and
    # collisions; the upload is renamed to ``{ids}{ext}`` after a
    # successful parse via ``move_file`` below.
    storage_name = f"{uuid.uuid4().hex}{file_extension.lower()}"
    upload_artifacts: list[str] = []

    try:
        # Validate (signature/size/MIME via safeuploads) and stream
        # the upload to disk in one unified step. The streaming
        # writer enforces the activity/gzip byte cap and writes via
        # a ``.part``-then-rename for atomicity.
        file_path = await core_file_uploads.save_validated_upload(
            file,
            kind=upload_kind,
            upload_dir=upload_dir,
            filename=storage_name,
            stream=True,
        )
        upload_artifacts.append(file_path)

        if file_extension.lower() == ".gz":
            original_file_path = file_path
            file_path, file_extension = await run_in_threadpool(
                handle_gzipped_file,
                file_path,
            )
            upload_artifacts.append(file_path)
            upload_artifacts.append(
                os.path.join(
                    core_config.FILES_PROCESSED_DIR,
                    os.path.basename(original_file_path),
                )
            )
            # Re-validate after decompression so the inner payload
            # still matches one of the supported activity formats.
            if file_extension.lower() not in core_config.SUPPORTED_FILE_FORMATS or file_extension.lower() == ".gz":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=("Decompressed file extension is not supported"),
                )
            # Defense in depth: signature-check the inner payload
            # via the same safeuploads validator used for direct
            # activity uploads.
            await core_file_uploads.validate_local_file(
                file_path,
                kind=core_file_uploads.UploadKind.ACTIVITY,
            )

        user = users_crud.get_user_by_id(token_user_id, db)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user_privacy_settings = users_privacy_settings_crud.get_user_privacy_settings_by_user_id(user.id, db)
        if user_privacy_settings is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User privacy settings not found",
            )

        # Parse the file in a thread pool to avoid
        # blocking the event loop with CPU-bound and
        # sync I/O work (gpxpy, geopy, timezonefinder)
        parsed_info = await run_in_threadpool(
            functools.partial(
                parse_file,
                token_user_id,
                user_privacy_settings,
                file_extension,
                file_path,
                db,
            )
        )

        if parsed_info is not None:
            created_activities = []
            ids_to_filename = ""
            if file_extension.lower() in (".gpx", ".tcx"):
                # Store the activity in the database
                created_activity = await store_activity(parsed_info, websocket_manager, db)
                created_activities.append(created_activity)
                ids_to_filename += str(created_activity.id)
            elif file_extension.lower() == ".fit":
                # Split the records by activity (check for multiple activities in the file)
                split_records_by_activity = fit_utils.split_records_by_activity(parsed_info)

                # Create activity objects for each activity in the file
                created_activities_objects = fit_utils.create_activity_objects(
                    split_records_by_activity,
                    token_user_id,
                    user_privacy_settings,
                    None,
                    None,
                    db,
                )

                for activity in created_activities_objects:
                    # Store the activity in the database
                    created_activity = await store_activity(activity, websocket_manager, db)
                    created_activities.append(created_activity)

                ids_to_filename = "_".join(str(activity.id) for activity in created_activities)
            else:
                core_logger.print_to_log_and_console(f"File extension not supported: {file_extension}", "error")

            # Define the directory where the processed files will be stored
            processed_dir = core_config.FILES_PROCESSED_DIR

            # Define new file path with activity ID as filename
            new_file_name = f"{ids_to_filename}{file_extension}"

            # Move the file to the processed directory
            move_file(processed_dir, new_file_name, file_path)

            for activity in created_activities:
                # Serialize the activity
                activity = serialize_activity(activity)

            # Return the created activity
            return created_activities
        else:
            await run_in_threadpool(_cleanup_upload_artifacts, upload_artifacts)
            return None
    except HTTPException:
        await run_in_threadpool(_cleanup_upload_artifacts, upload_artifacts)
        raise
    except (
        OSError,
        EOFError,
        gzip.BadGzipFile,
        shutil.Error,
        SQLAlchemyError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
    ) as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in parse_and_store_activity_from_uploaded_file - {err!s}",
            "error",
            exc=err,
        )
        await run_in_threadpool(_cleanup_upload_artifacts, upload_artifacts)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def move_file(new_dir: str, new_filename: str, file_path: str) -> None:
    """Move ``file_path`` into ``new_dir`` as ``new_filename``.

    Thin compatibility wrapper around
    :func:`core.file_uploads.move_within`. New code should call
    ``move_within`` directly so callers benefit from path
    containment without an intermediate hop.

    Args:
        new_dir: Destination directory (created if missing).
        new_filename: Final filename inside ``new_dir``.
        file_path: Source path to move.

    Raises:
        HTTPException: 400 for unsafe filename / containment
            violations, 500 for I/O failures.
    """
    core_file_uploads.move_within(file_path, new_dir, filename=new_filename)


def parse_file(
    token_user_id: int,
    user_privacy_settings: users_privacy_settings_models.UsersPrivacySettings,
    file_extension: str,
    filename: str,
    db: Session,
    activity_name: str | None = None,
) -> dict | None:
    try:
        if filename.lower() != "bulk_import/__init__.py":
            core_logger.print_to_log(f"Parsing file: {filename}")
            # Choose the appropriate parser based on file extension
            if file_extension.lower() == ".gpx":
                # Parse the GPX file
                parsed_info = gpx_utils.parse_gpx_file(
                    filename,
                    token_user_id,
                    user_privacy_settings,
                    db,
                    activity_name,
                )
            elif file_extension.lower() == ".tcx":
                parsed_info = tcx_utils.parse_tcx_file(
                    filename,
                    token_user_id,
                    user_privacy_settings,
                    db,
                    activity_name,
                )
            elif file_extension.lower() == ".fit":
                # Parse the FIT file
                parsed_info = fit_utils.parse_fit_file(filename, db, activity_name)
            else:
                # file extension not supported raise an HTTPException with a 406 Not Acceptable status code
                raise HTTPException(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    detail="File extension not supported. Supported file extensions are .gpx, .fit and .tcx",
                )
            return parsed_info
        else:
            return None
    except HTTPException as http_err:
        raise http_err
    except (
        OSError,
        EOFError,
        gzip.BadGzipFile,
        SQLAlchemyError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
    ) as err:
        # Log the exception with full traceback but return a generic
        # error message to the caller to avoid internal info disclosure.
        core_logger.print_to_log(f"Error in parse_file - {err}", "error", exc=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


async def store_activity(
    parsed_info: dict,
    websocket_manager: websocket_manager.WebSocketManager,
    db: Session,
) -> activities_schema.Activity:
    # create the activity in the database
    created_activity = await activities_crud.create_activity(parsed_info["activity"], websocket_manager, db)

    # Check if created_activity is None
    if created_activity is None or created_activity.id is None:
        # Log the error
        core_logger.print_to_log(
            "Error in store_activity - activity is None, error creating activity",
            "error",
        )
        # raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating activity",
        )

    # Parse the activity streams from the parsed info
    activity_streams = parse_activity_streams_from_file(parsed_info, created_activity.id)

    if activity_streams is not None:
        # Create activity streams in the database
        await activity_streams_crud.create_activity_streams(activity_streams, created_activity, db)

    if parsed_info.get("laps") is not None:
        # Create activity laps in the database
        activity_laps_crud.create_activity_laps(parsed_info["laps"], created_activity.id, db)

    if parsed_info.get("workout_steps") is not None:
        # Create activity workout steps in the database
        activity_workout_steps_crud.create_activity_workout_steps(parsed_info["workout_steps"], created_activity.id, db)

    if parsed_info.get("sets") is not None:
        # Create activity sets in the database
        activity_sets_crud.create_activity_sets(parsed_info["sets"], created_activity.id, db)

    # Generate a static map thumbnail if GPS data is present
    if parsed_info.get("is_lat_lon_set") and parsed_info.get("lat_lon_waypoints"):
        server_settings = server_settings_crud.get_server_settings(db)
        tile_url = server_settings.tileserver_url if server_settings else activities_thumbnail._DEFAULT_TILE_URL
        bg_color = server_settings.map_background_color if server_settings else activities_thumbnail._DEFAULT_BG_COLOR
        # Decrypt tile API key if the provider requires backend auth
        api_key = None
        if server_settings and server_settings.tileserver_api_key:
            api_key = core_cryptography.decrypt_token_fernet(server_settings.tileserver_api_key)
        thumbnail_path = activities_thumbnail.generate_activity_thumbnail(
            created_activity.id,
            parsed_info["lat_lon_waypoints"],
            core_config.settings.ACTIVITY_THUMBNAILS_DIR,
            tile_url=tile_url,
            background_color=bg_color,
            api_key=api_key,
        )
        if thumbnail_path is not None:
            activities_crud.set_activity_thumbnail_path(
                created_activity.id,
                thumbnail_path,
                db,
            )

    # Return the created activity
    return created_activity


def parse_activity_streams_from_file(parsed_info: dict, activity_id: int):
    # Create a dictionary mapping stream types to is_set keys and waypoints keys
    stream_mapping = {
        1: ("is_heart_rate_set", "hr_waypoints"),
        2: ("is_power_set", "power_waypoints"),
        3: ("is_cadence_set", "cad_waypoints"),
        4: ("is_elevation_set", "ele_waypoints"),
        5: ("is_velocity_set", "vel_waypoints"),
        6: ("is_velocity_set", "pace_waypoints"),
        7: ("is_lat_lon_set", "lat_lon_waypoints"),
        8: ("is_temperature_set", "temp_waypoints"),
    }

    # Create a list of tuples containing stream type, is_set, and waypoints
    stream_data_list = [
        (
            stream_type,
            (is_set_key(parsed_info) if callable(is_set_key) else parsed_info.get(is_set_key, False)),
            parsed_info.get(waypoints_key, []),
        )
        for stream_type, (is_set_key, waypoints_key) in stream_mapping.items()
        if (is_set_key(parsed_info) if callable(is_set_key) else parsed_info.get(is_set_key, False))
    ]

    # Return activity streams as a list of ActivityStreams objects
    return [
        activity_streams_schema.ActivityStreamsCreate(
            activity_id=activity_id,
            stream_type=stream_type,
            stream_waypoints=waypoints,
            strava_activity_stream_id=None,
        )
        for stream_type, is_set, waypoints in stream_data_list
    ]


def calculate_activity_stats(
    activities: list[activities_schema.Activity],
) -> activities_schema.ActivityStats:
    """Aggregate distance (m), time (s), and calories per sport type.

    Args:
        activities: List of Activity schema objects for the timeframe.

    Returns:
        ActivityStats with per-sport distance, time, and calories totals.
    """
    stats = activities_schema.ActivityStats()

    if activities is None:
        return stats

    # Sport-type buckets: activity_type IDs → attribute name on ActivityStats
    _sport_buckets: list[tuple[list[int], str]] = [
        ([1, 2, 3, 34, 40], "run"),
        ([4, 5, 6, 7, 27, 28, 29, 35, 36], "bike"),
        ([8, 9], "swim"),
        ([11, 31], "walk"),
        ([12], "hike"),
        ([13], "rowing"),
        ([15, 16], "snow_ski"),
        ([17], "snowboard"),
        ([30], "windsurf"),
        ([32], "stand_up_paddleboarding"),
        ([33], "surfing"),
        ([42], "kayaking"),
        ([43], "sailing"),
        ([44], "snowshoeing"),
        ([45], "inline_skating"),
    ]

    try:
        for activity in activities:
            for type_ids, bucket_name in _sport_buckets:
                if activity.activity_type in type_ids:
                    bucket = getattr(stats, bucket_name)
                    bucket.distance += float(activity.distance or 0)
                    bucket.time += float(activity.total_timer_time or 0)
                    bucket.calories += float(activity.calories or 0)
                    break
    except (TypeError, ValueError, AttributeError) as err:
        core_logger.print_to_log(f"Error in calculate_activity_stats - {err!s}", "error", exc=err)

    return stats


def location_based_on_coordinates(latitude: float | None, longitude: float | None) -> dict | None:
    """Reverse-geocode a (lat, lon) pair into a location dict.

    Args:
        latitude: Latitude in decimal degrees, or ``None``.
        longitude: Longitude in decimal degrees, or ``None``.

    Returns:
        Dict with ``city``/``town``/``country`` keys (all non-None), or
        ``None`` when no provider is configured, coordinates are missing,
        all geocoded fields are empty, or the provider returns an error.
    """
    # Check if latitude and longitude are provided
    if latitude is None or longitude is None:
        return None

    # Create a dictionary with the parameters for the request
    if core_config.settings.REVERSE_GEO_PROVIDER == "nominatim":
        # Create the URL for the request
        url_params = {
            "format": "jsonv2",
            "lat": latitude,
            "lon": longitude,
        }
        protocol = "https"
        if not core_config.settings.NOMINATIM_API_USE_HTTPS:
            protocol = "http"
        url = f"{protocol}://{core_config.settings.NOMINATIM_API_HOST}/reverse?{urlencode(url_params)}"
    elif core_config.settings.REVERSE_GEO_PROVIDER == "photon":
        # Create the URL for the request
        url_params = {
            "lat": latitude,
            "lon": longitude,
        }
        protocol = "https"
        if not core_config.settings.PHOTON_API_USE_HTTPS:
            protocol = "http"
        url = f"{protocol}://{core_config.settings.PHOTON_API_HOST}/reverse?{urlencode(url_params)}"
    elif core_config.settings.REVERSE_GEO_PROVIDER == "geocode":
        # Check if the API key is set
        if core_config.settings.GEOCODES_MAPS_API == "changeme":
            return None
        # Create the URL for the request
        url_params = {
            "lat": latitude,
            "lon": longitude,
            "api_key": core_config.settings.GEOCODES_MAPS_API,
        }
        url = f"https://geocode.maps.co/reverse?{urlencode(url_params)}"
    else:
        # If no provider is set, return None
        return None

    # Throttle requests according to configured rate limit
    if core_config.REVERSE_GEO_MIN_INTERVAL > 0:
        with core_config.REVERSE_GEO_LOCK:
            now = time.monotonic()
            interval = core_config.REVERSE_GEO_MIN_INTERVAL - (now - core_config.REVERSE_GEO_LAST_CALL)
            if interval > 0:
                time.sleep(interval)
            core_config.REVERSE_GEO_LAST_CALL = time.monotonic()

    # Make the request and get the response
    try:
        headers = {"User-Agent": f"Endurain/{core_config.API_VERSION} (ReverseGeocoding)"}
        # Make the request and get the response
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        if core_config.settings.REVERSE_GEO_PROVIDER in ("geocode", "nominatim"):
            # Get the data from the response
            data = response.json().get("address", {})
            # Return the location based on the coordinates
            # Note: 'town' is used for district in Geocode API
            city = data.get("city")
            town = data.get("town")
            country = data.get("country")
            if any([city, town, country]):
                return {
                    "city": city,
                    "town": town,
                    "country": country,
                }
            return None

        # Get the data from the response
        data_root = response.json().get("features", [])
        data = data_root[0].get("properties", {}) if data_root else {}
        # Return the location based on the coordinates
        # Note: 'district' is used for city and 'city' is used for town in Photon API
        city = data.get("district")
        town = data.get("city")
        country = data.get("country")
        if any([city, town, country]):
            return {
                "city": city,
                "town": town,
                "country": country,
            }
        return None
    except Exception as err:
        # Log the error; return None so the activity import can continue
        # without location data rather than aborting the whole operation.
        core_logger.print_to_log_and_console(f"Error in location_based_on_coordinates - {err}", "error")
        return None


def append_if_not_none(
    waypoint_list: list[dict],
    waypoint_time,
    value,
    key: str,
) -> None:
    """Append ``{time, key: value}`` to ``waypoint_list`` if value is set.

    Args:
        waypoint_list: List to mutate in place.
        waypoint_time: Timestamp associated with the value.
        value: The value to record; ignored when ``None``.
        key: Dict key under which ``value`` is stored.
    """
    if value is not None:
        waypoint_list.append({"time": waypoint_time, key: value})


def calculate_instant_speed(
    prev_time,
    waypoint_time,
    latitude: float,
    longitude: float,
    prev_latitude: float | None,
    prev_longitude: float | None,
) -> float:
    """Compute m/s speed between two GPS waypoints.

    Args:
        prev_time: Previous waypoint timestamp; ``None`` returns 0.
        waypoint_time: Current waypoint timestamp.
        latitude: Current latitude (decimal degrees).
        longitude: Current longitude (decimal degrees).
        prev_latitude: Previous latitude (decimal degrees).
        prev_longitude: Previous longitude (decimal degrees).

    Returns:
        Instantaneous speed in m/s, or 0 when the time delta is
        non-positive or ``prev_time`` is missing.
    """
    if prev_time is None or prev_latitude is None or prev_longitude is None:
        return 0

    time_difference = (waypoint_time - prev_time).total_seconds()

    if time_difference <= 0:
        return 0

    distance = geodesic(
        (prev_latitude, prev_longitude),
        (latitude, longitude),
    ).meters
    return distance / time_difference


def compute_elevation_gain_and_loss(
    elevations: list[dict],
    median_window: int = 6,
    avg_window: int = 3,
    threshold: float = 0.1,
) -> tuple[float, float]:
    """Compute total elevation gain/loss in meters from waypoints.

    Applies a median filter then a moving-average smoother before
    summing per-step deltas above ``threshold``.

    Args:
        elevations: List of dicts with an ``ele`` key (meters).
        median_window: Window size for the median pre-filter.
        avg_window: Window size for the moving-average smoother.
        threshold: Minimum |delta| (m) counted toward gain/loss.

    Returns:
        Tuple of (gain_m, loss_m).
    """

    # 1) Median Filter
    def median_filter(values, window_size):
        if window_size < 2:
            return values[:]
        half = window_size // 2
        filtered = []
        for i in range(len(values)):
            start = max(0, i - half)
            end = min(len(values), i + half + 1)
            window_vals = values[start:end]
            m = statistics.median(window_vals)
            filtered.append(m)
        return filtered

    # 2) Moving-Average Smoothing
    def moving_average(values, window_size):
        if window_size < 2:
            return values[:]
        half = window_size // 2
        smoothed = []
        n = len(values)
        for i in range(n):
            start = max(0, i - half)
            end = min(n, i + half + 1)
            window_vals = values[start:end]
            smoothed.append(statistics.mean(window_vals))
        return smoothed

    try:
        # Get the values from the elevations
        values = [float(waypoint["ele"]) for waypoint in elevations]
    except (ValueError, KeyError):
        # If there are no valid values, return 0
        return 0, 0

    # Apply median filter -> then average smoothing
    filtered = median_filter(values, median_window)
    filtered = moving_average(filtered, avg_window)

    # 3) Compute gain/loss with threshold
    total_gain = 0.0
    total_loss = 0.0
    for i in range(1, len(filtered)):
        diff = filtered[i] - filtered[i - 1]
        if diff > threshold:
            total_gain += diff
        elif diff < -threshold:
            total_loss -= diff  # diff is negative, so subtracting it is adding positive
    return total_gain, total_loss


def calculate_pace(
    distance: float,
    first_waypoint_time,
    last_waypoint_time,
) -> float:
    """Compute average pace (seconds per meter).

    Args:
        distance: Total distance in meters.
        first_waypoint_time: Datetime of the first waypoint.
        last_waypoint_time: Datetime of the last waypoint.

    Returns:
        Pace in s/m, or 0 when ``distance`` is 0.
    """
    # If the distance is 0, return 0
    if distance == 0:
        return 0

    # Convert the time strings to datetime objects
    start_datetime = datetime.fromisoformat(first_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S"))
    end_datetime = datetime.fromisoformat(last_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S"))

    # Calculate the time difference in seconds
    total_time_in_seconds = (end_datetime - start_datetime).total_seconds()

    # Calculate pace in seconds per meter
    pace_seconds_per_meter = total_time_in_seconds / distance

    # Return the pace
    return pace_seconds_per_meter


def calculate_avg_and_max(data: list[dict], stream_type: str, exclude_zeros: bool = False) -> tuple[float, float]:
    """Compute the mean and max of ``stream_type`` across waypoints.

    Zero values are always excluded when ``stream_type`` is ``"hr"`` because
    zero is not a physiologically valid heart rate — it is a sentinel emitted
    by sensors when they lose signal. Callers may also set ``exclude_zeros``
    explicitly for other stream types.

    Args:
        data: List of waypoint dicts.
        stream_type: Key to read from each waypoint.
        exclude_zeros: When ``True``, values equal to zero are excluded.
            Automatically ``True`` when ``stream_type`` is ``"hr"``.

    Returns:
        Tuple of (avg, max), or (0, 0) when no values are present.
    """
    try:
        # Get the values from the data
        values = [float(waypoint[stream_type]) for waypoint in data if waypoint.get(stream_type) is not None]
    except (ValueError, KeyError, TypeError):
        # If there are no valid values, return 0
        return 0, 0

    if exclude_zeros or stream_type == "hr":
        values = [v for v in values if v != 0]

    if not values:
        return 0, 0

    # Calculate the average and max values
    avg_value = mean(values)
    max_value = max(values)

    return avg_value, max_value


def calculate_np(data: list[dict]) -> float:
    """Compute Normalized Power (NP) from power waypoints.

    Args:
        data: List of waypoint dicts with a ``power`` key.

    Returns:
        Normalized Power in watts, or 0 when no values are present.
    """
    try:
        # Get the power values from the data
        values = [float(waypoint["power"]) for waypoint in data if waypoint["power"] is not None]
    except (ValueError, KeyError, TypeError):
        # If there are no valid values, return 0
        return 0

    if not values:
        return 0

    # Calculate the fourth power of each power value
    fourth_powers = [p**4 for p in values]

    # Calculate the average of the fourth powers
    avg_fourth_power = sum(fourth_powers) / len(fourth_powers)

    # Take the fourth root of the average of the fourth powers to get Normalized Power
    normalized_power = avg_fourth_power ** (1 / 4)

    return normalized_power


def define_activity_type(activity_type_name: str) -> int:
    """
    Maps an activity type name (string) to its corresponding ID (integer).
    Uses the global ACTIVITY_NAME_TO_ID dictionary.
    Returns 10 (Workout) if the name is not found.
    """
    # Default value
    default_type_id = 10

    # Get the activity type ID from the global mapping (case-insensitive)
    # Ensure input is a string before lowercasing
    if isinstance(activity_type_name, str):
        return ACTIVITY_NAME_TO_ID.get(activity_type_name.lower(), default_type_id)
    else:
        # Handle non-string input if necessary, or return default
        return default_type_id


def set_activity_name_based_on_activity_type(activity_type_id: int) -> str:
    """
    Maps an activity type ID (integer) to its corresponding name (string).
    Uses the global ACTIVITY_ID_TO_NAME dictionary.
    Returns "Workout" if the ID is not found or is 10.
    Appends " workout" suffix if the name is not "Workout".
    """
    # Get the mapping for the activity type ID, default to "Workout"
    mapping = ACTIVITY_ID_TO_NAME.get(activity_type_id, "Workout")

    # If type is not 10 (Workout), return the mapping with " workout" suffix
    return mapping + " workout" if mapping != "Workout" else mapping


def process_all_files_sync(
    user_id: int,
    file_paths: list[str],
    websocket_manager: websocket_manager.WebSocketManager,
    import_initiated_time: str,
):
    """
    Process all files sequentially in single thread.

    Args:
        user_id: User ID.
        file_paths: List of file paths to process.
        websocket_manager: WebSocket manager instance.
    """
    db = next(core_database.get_db())
    try:
        total_files = len(file_paths)
        for idx, file_path in enumerate(file_paths, 1):
            core_logger.print_to_log_and_console(f"Processing file {idx}/{total_files}: {file_path}")
            asyncio.run(
                parse_and_store_activity_from_file(
                    user_id,
                    file_path,
                    websocket_manager,
                    db,
                    is_bulk_import=True,
                    import_initiated_time=import_initiated_time,
                )
            )
            # Small delay between files
            time.sleep(0.1)

        core_logger.print_to_log_and_console(f"Bulk import completed: {total_files} files processed for user {user_id}")
    finally:
        db.close()


def delete_and_regenerate_all_activity_thumbnails() -> None:
    """
    Delete all existing thumbnails and regenerate from scratch.

    Called when the tile server settings change and the admin has
    enabled automatic thumbnail regeneration. Clears all thumbnail
    file references in the database, deletes the files on disk,
    then triggers a full regeneration pass.

    Returns:
        None

    Raises:
        None — errors are logged; execution continues.
    """
    core_logger.print_to_log(
        "Thumbnail regeneration: deleting all existing thumbnails",
        "info",
    )

    # Clear DB references so generate_missing picks them all up
    with core_database.SessionLocal() as db:
        activities_crud.clear_all_activity_thumbnail_paths(db)

    # Delete files from disk
    thumbnails_dir = Path(core_config.settings.ACTIVITY_THUMBNAILS_DIR)
    deleted = 0
    if thumbnails_dir.is_dir():
        for thumb_file in thumbnails_dir.glob("*.png"):
            try:
                thumb_file.unlink()
                deleted += 1
            except OSError as err:
                core_logger.print_to_log(
                    f"Thumbnail regeneration: could not delete {thumb_file}: {err}",
                    "warning",
                )

    core_logger.print_to_log(
        f"Thumbnail regeneration: deleted {deleted} file(s) from disk",
        "info",
    )

    # Regenerate all thumbnails
    generate_missing_activity_thumbnails()


def generate_missing_activity_thumbnails() -> None:
    """
    Generate thumbnails for activities that are missing one.

    Intended to be called periodically by the scheduler. Opens
    its own database session, queries for activities whose
    map_thumbnail_path is NULL, fetches the GPS stream for each,
    and generates + persists the thumbnail.

    Returns:
        None

    Raises:
        None — errors are logged per-activity; execution continues.
    """
    with core_database.SessionLocal() as db:
        activities_with_thumbnail = activities_crud.get_activities_with_thumbnail(db)
        for activity in activities_with_thumbnail:
            thumb_path = Path(activity.map_thumbnail_path)
            if not thumb_path.is_file():
                activities_crud.set_activity_thumbnail_path(activity.id, None, db)
                core_logger.print_to_log(
                    f"Thumbnail scheduler: missing file for activity {activity.id}, cleared thumbnail path in DB",
                    "info",
                )

        activities_without_thumbnail = activities_crud.get_activities_without_thumbnail(db)

        if not activities_without_thumbnail:
            core_logger.print_to_log(
                "Thumbnail scheduler: no activities without thumbnail found",
                "debug",
            )
            return

        core_logger.print_to_log(
            f"Thumbnail scheduler: generating thumbnails for {len(activities_without_thumbnail)} activities",
            "info",
        )

        server_settings = server_settings_crud.get_server_settings(db)
        tile_url = server_settings.tileserver_url if server_settings else activities_thumbnail._DEFAULT_TILE_URL
        bg_color = server_settings.map_background_color if server_settings else activities_thumbnail._DEFAULT_BG_COLOR
        api_key = None
        if server_settings and server_settings.tileserver_api_key:
            api_key = core_cryptography.decrypt_token_fernet(server_settings.tileserver_api_key)

        activity_ids = [activity.id for activity in activities_without_thumbnail]
        gps_streams = (
            db.execute(
                select(activity_streams_models.ActivityStreams).where(
                    activity_streams_models.ActivityStreams.activity_id.in_(activity_ids),
                    activity_streams_models.ActivityStreams.stream_type == activity_streams_constants.STREAM_TYPE_MAP,
                )
            )
            .scalars()
            .all()
        )
        gps_streams_by_activity_id = {stream.activity_id: stream for stream in gps_streams}

        generated = 0
        for activity in activities_without_thumbnail:
            gps_stream = gps_streams_by_activity_id.get(activity.id)

            if not gps_stream or not gps_stream.stream_waypoints:
                continue

            thumbnail_path = activities_thumbnail.generate_activity_thumbnail(
                activity.id,
                gps_stream.stream_waypoints,
                core_config.settings.ACTIVITY_THUMBNAILS_DIR,
                tile_url=tile_url,
                background_color=bg_color,
                api_key=api_key,
            )

            if thumbnail_path is not None:
                activities_crud.set_activity_thumbnail_path(activity.id, thumbnail_path, db)
                generated += 1

        core_logger.print_to_log(
            f"Thumbnail scheduler: generated {generated} "
            f"thumbnail(s) out of "
            f"{len(activities_without_thumbnail)} candidate(s)",
            "info",
        )
