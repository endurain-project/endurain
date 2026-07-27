import asyncio
import os
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.file_uploads as file_uploads
import core.logger as core_logger
import core.text_imports as core_text_imports
import core.timezone as core_timezone
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.bulk_entry as ingestion_bulk_entry
import modules.activities.activity_ingestion.sources as ingestion_sources
import modules.activities.activity_media.crud as activity_media_crud
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.crud as gears_crud
import modules.users.users.crud as users_crud
import modules.websocket.manager as websocket_manager

logger = core_logger.get_logger(__name__)

_STRAVA_ACTIVITIES_HEADERS = {
    "Filename",
    "Activity Description",
    "Activity Gear",
    "Activity ID",
    "Media",
    "Activity Date",
    "Activity Name",
    "Activity Type",
}


def iterate_over_activities_csv() -> dict | None:
    """
    Parses information in a Strava activities.csv file.

    Returns: Dictionary that contains the activities.csv file data.  Dictionary uses each activity's filename as the key.
    """
    # Ensure the 'strava_import' directory exists (.csv files will be here)
    strava_import_dir = core_config.STRAVA_BULK_IMPORT_DIR
    os.makedirs(strava_import_dir, exist_ok=True)

    # Build activities file path
    strava_activities_file_name = core_config.STRAVA_BULK_IMPORT_ACTIVITIES_FILE
    strava_activities_file = os.path.join(strava_import_dir, strava_activities_file_name)

    # Importing data from Strava activities file.
    # Using Python's core CSV module here - https://docs.python.org/3/library/csv.html
    if os.path.isfile(strava_activities_file):
        logger.debug(
            f"Strava {strava_activities_file_name} file present. Going to try to parse it.",
            extra=core_logger.context(console=True),
        )
        try:
            strava_activities_dict = {}
            for row in core_text_imports.read_bounded_csv(strava_activities_file):
                # Check to see if file has headers that will be used during parsing of the file.
                missing_headers = _STRAVA_ACTIVITIES_HEADERS - row.keys()
                if missing_headers:
                    logger.error(
                        "Aborting Strava bulk activities import: Proper headers not found in "
                        f"{strava_activities_file_name}. Missing: "
                        f"{', '.join(sorted(missing_headers))}.",
                        extra=core_logger.context(console=True),
                    )
                    return None
                _, strava_act_file_name = os.path.split(
                    row["Filename"]
                )  # strips path, returns filename with extension.
                strava_activities_dict[strava_act_file_name] = (
                    row  # Store activity information in a dictionary using filename as the key
                )
            logger.info(
                f"Strava bulk import: Strava activities csv file parsed, and it is {len(strava_activities_dict)} rows long",
                extra=core_logger.context(console=True),
            )
            return strava_activities_dict
        except HTTPException as http_err:
            # ``read_bounded_csv`` raises HTTP 413/424 for oversized
            # files or stat/open failures. Surface the structured
            # detail so the operator sees the actual cause instead
            # of a generic ``None`` return.
            logger.error(
                f"Strava activities CSV parsing aborted: {http_err.detail}", extra=core_logger.context(console=True)
            )
            return None
        except Exception as err:
            logger.error(
                f"Strava activities CSV parsing failed with error: {err}.", extra=core_logger.context(console=True)
            )
            return None
    else:
        logger.error(
            f"Strava bulk import: Strava activities file not found. File should be at: {strava_activities_file}",
            extra=core_logger.context(console=True),
        )
        return None


def create_gear_dictionary_for_bulk_import(
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> dict | None:
    """
    Creates a dictionary that links gear nicknames in Endurain to their Endurain gear IDs.

    The dictionary includes both base Endurain gear nickname and the gear name smoosh ("{brand} {model} {name}") that Strava uses for its shoe gear listing in activities.csv

    Returns: Dictionary that uses the gear name as a key to look up the gear ID.
    """
    user = users_crud.get_user_by_id(token_user_id, db)
    if user is not None:
        user_gear_list = gears_crud.get_gear_user(user.id, db)
        if user_gear_list is None:
            # User has no gear.
            users_existing_gear_nickname_to_id = None
        else:
            # User has gear - build dictionary to facilitate gear to ID work during import.
            users_existing_gear_nickname_to_id = {}
            for item in user_gear_list:
                users_existing_gear_nickname_to_id[item.nickname] = [item.id]
                # Strava apparently exports shoe names as a smoosh of "{brand} {model} {name}", so adding that as a second key for each gear item
                strava_name_smoosh = " ".join(
                    part
                    for part in [
                        (item.brand or "").strip(),
                        (item.model or "").strip(),
                        (item.nickname or "").strip(),
                    ]
                    if part
                )
                if strava_name_smoosh not in users_existing_gear_nickname_to_id:
                    users_existing_gear_nickname_to_id[strava_name_smoosh] = [item.id]
        return users_existing_gear_nickname_to_id
    return None


def queue_bulk_export_activities_for_import(
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    websocket_manager: websocket_manager.WebSocketManager,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    strava_activities_dict: dict,
    users_existing_gear_nickname_to_id: dict,
    import_time: str,
) -> int:
    """
    Queues files located in the Strava bulk import activities directory for processing.  Process all files sequentially in single thread (similar to activity/utils.process_all_files_sync()).

    Returns: Number of files that were queued (which is not used currently by the calling function)
    """

    # Ensure the 'strava_import/activities' directory exists (activity files will be here)
    strava_activities_import_dir = core_config.STRAVA_BULK_IMPORT_ACTIVITIES_DIR
    os.makedirs(strava_activities_import_dir, exist_ok=True)

    # Ensure the 'strava_import/media' directory exists (media files will be here)
    strava_media_import_dir = core_config.STRAVA_BULK_IMPORT_MEDIA_DIR
    os.makedirs(strava_media_import_dir, exist_ok=True)

    # Grab list of supported file formats
    supported_file_formats = core_config.SUPPORTED_FILE_FORMATS

    # Get file list of all files in the 'strava_import/activities' directory
    filelist = os.listdir(strava_activities_import_dir)

    # Get total file count and log it
    totalfilecount = len(filelist)
    logger.info(
        f"Strava bulk import: Found {totalfilecount} files in the {strava_activities_import_dir}.",
        extra=core_logger.context(console=True),
    )

    # Build a list of importable files. Validation is async (it
    # wraps each file in an UploadFile and runs the safeuploads
    # pipeline) so the whole batch is driven by a single
    # ``asyncio.run`` to avoid one event-loop setup per file and to
    # stay safe if this function is ever called from a sync code
    # path that does not already own a loop.
    async def _scan_and_validate() -> tuple[list[str], int]:
        importable: list[str] = []
        skipped = 0
        for fname in filelist:
            fpath = os.path.join(strava_activities_import_dir, fname)

            # Check if file is one we can process
            _, fext = os.path.splitext(fpath)
            if fext not in supported_file_formats:
                logger.warning(
                    f"Strava bulk import: Skipping file {fpath} - "
                    "due to not having a supported file extension. "
                    f"Supported extensions are: {supported_file_formats}.",
                    extra=core_logger.context(console=True),
                )
                skipped += 1
                continue

            # Validate the on-disk file through the unified pipeline
            # so arbitrary bytes with a supported extension cannot
            # reach the activity parser.
            entry_kind = file_uploads.UploadKind.GZIP if fext.lower() == ".gz" else file_uploads.UploadKind.ACTIVITY
            try:
                await file_uploads.validate_local_file(fpath, kind=entry_kind, filename=fname)
            except HTTPException as err:
                logger.warning(
                    f"Strava bulk import: Skipping file {fpath} - failed validation: {err.detail}",
                    extra=core_logger.context(console=True),
                )
                skipped += 1
                continue

            importable.append(fname)
        return importable, skipped

    importable_files, skippedprocessingcount = asyncio.run(_scan_and_validate())
    # Note: ``asyncio.run`` is safe here because this function is
    # dispatched via ``loop.run_in_executor`` from
    # ``strava/router.py`` (worker thread, no running event loop).
    # If a future caller invokes this from an async context, switch
    # to ``await _scan_and_validate()`` and make this function async.

    # Check if there are any importable files and log status
    number_of_importable_files = len(importable_files)
    if number_of_importable_files == 0:
        logger.warning(
            f"Strava bulk import:There are no importable files in {strava_activities_import_dir} directory - aborting import.",
            extra=core_logger.context(console=True),
        )
        return 0
    logger.info(
        f"Strava bulk import: Skipped a total of {skippedprocessingcount} files due to not having a supported file extension. There are now {number_of_importable_files} files to queue for processing. ",
        extra=core_logger.context(console=True),
    )

    # Iterate over each importable file and queue import
    filenumber = 0
    queuedforprocessingcount = 0
    for filename in importable_files:
        filenumber += 1
        file_path = os.path.join(strava_activities_import_dir, filename)

        if os.path.isfile(file_path):
            logger.info(
                f"Strava bulk import: Processing file {filenumber} of {number_of_importable_files} - {file_path}",
                extra=core_logger.context(console=True),
            )
            # Parse and store the activity. The ingestion entry is
            # synchronous; this queue function runs on a worker thread
            # (dispatched via ``loop.run_in_executor`` from
            # ``strava/router.py``) with no running event loop, so the
            # sync file-validation inside it is safe.
            ingestion_bulk_entry.store_activity_file(
                token_user_id,
                file_path,
                db,
                source=ingestion_sources.BulkImportSource(
                    import_initiated_time=import_time,
                    strava_activities=strava_activities_dict,
                    gear_nickname_to_id=users_existing_gear_nickname_to_id,
                ),
            )
            # Small delay between files
            time.sleep(0.1)

    logger.info(
        f"Strava bulk import: Import complete! A total of {filenumber} files were processed.",
        extra=core_logger.context(console=True),
    )

    return queuedforprocessingcount


def build_metadata_dict(
    file_base_name: str,  # String with the base filename being processed (also key to strava_activities dictionary)
    strava_activities: dict,  # dictionary with info for a Strava bulk import - format strava_activities["filename"]["column header from Strava activities spreadsheet"]
    import_initiated_time: str,  # String containing the time the Strava bulk import was initiated.
    users_existing_gear_nickname_to_id: dict
    | None = None,  # Dictionary containing gear nickname to ID, needed for Strava bulk import
) -> dict:
    """
    Creates a dictionary with metadata information pulled from a Strava activities file.

    The field strava_activity_metadata["metadata_found_in_csv"] identifies whether there was an entry for this activity in the activities.csv file or not.

    Returns: Dictionary that contains the gear name as a key to look up the gear ID.
    """
    strava_activity_metadata: dict[str, Any] = {}
    if isinstance(strava_activities, dict) and strava_activities.get(
        file_base_name
    ):  # We have information on the activity
        # Strava bulk import notes:
        #     Importing Strava activity id to the activity's "strava_activity_id" field results in Endurain thinking the activity is linked to Strava via the Strava active linking mechanism.
        #     Strava media will be worked on after the activity has been created, so it is not dealt with here.
        strava_activity_metadata["name"] = strava_activities[file_base_name]["Activity Name"]
        strava_activity_metadata["description"] = strava_activities[file_base_name]["Activity Description"]
        strava_activity_metadata["activity type"] = strava_activities[file_base_name]["Activity Type"]

        # Needed for checking for duplicates within multi-file .fit file Strava bulk imports
        strava_activity_metadata["activity date"] = strava_activities[file_base_name]["Activity Date"]

        # Gear work
        activity_gear = None
        activity_gear = strava_activities[file_base_name]["Activity Gear"]
        if activity_gear and activity_gear is not None:
            if activity_gear.replace("+", " ").strip() in users_existing_gear_nickname_to_id:
                # Gear names in Endurain have all +'s swapped to spaces, thus need to do this here as well.
                strava_activity_metadata["gear_id"] = users_existing_gear_nickname_to_id[activity_gear][0]
            else:
                strava_activity_metadata["gear_id"] = None
                logger.info(
                    f"Bulk file import: Gear for activity {file_base_name}, which activities.csv shows as {activity_gear}, was not found in the user's existing gear. Not adding gear to activity.",
                    extra=core_logger.context(console=True),
                )
        else:
            strava_activity_metadata["gear_id"] = None
        import_dict = build_import_dictionary(file_base_name, import_initiated_time, True, strava_activities)
        strava_activity_metadata["import_dict"] = import_dict
        strava_activity_metadata["metadata_found_in_csv"] = True  # We found metadata in the CSV!
        logger.info(
            f"Bulk file import: Strava activities.csv metadata extracted for activity {file_base_name}.",
            extra=core_logger.context(console=True),
        )
    else:
        # We are in a Strava import, but don't have data on the file.  Just do a basic metadata addition.
        import_dict = build_import_dictionary(file_base_name, import_initiated_time, False)
        strava_activity_metadata["metadata_found_in_csv"] = (
            False  # No metadata found in CSV, so don't try to add it in later.
        )
        strava_activity_metadata["import_dict"] = import_dict

        logger.info(
            f"Bulk file import: No data in Strava activities.csv file for activity {file_base_name}.",
            extra=core_logger.context(console=True),
        )

    return strava_activity_metadata


def build_import_dictionary(
    file_base_name: str,  # String with the base filename being processed (also key to strav_activities dictionary)
    import_initiated_time: str,  # String containing the time the Strava bulk import was initiated.
    is_strava_bulk_import: bool = False,  # Boolean to track if we are doing a Strava bulk import or not
    strava_activities: dict
    | None = None,  # dictionary with info for a Strava bulk import - format strava_activities["filename"]["column header from Strava activities spreadsheet"]
) -> dict:
    """
    Creates the "import_info" dictionary that is added to all activities that are imported from files.

    Functions both for Strava imports and generic bulk imports, depending on whether the is_strava_bulk_import variable is set or not.

    Returns: Dictionary that contains the import_dict values for the activity (which is then added to the activity as a dictionary in the "import_info" field of the activity).
    """
    import_dict: dict[str, Any] = {}
    if is_strava_bulk_import:
        import_dict["imported"] = True
        import_dict["import_source"] = "Strava bulk import"
        activity_id_value = strava_activities[file_base_name].get("Activity ID", "")
        if activity_id_value:
            try:
                import_dict["strava_activity_id"] = int(activity_id_value)
            except (TypeError, ValueError):
                logger.warning(
                    f"Bulk file import: Ignoring invalid Strava Activity ID for {file_base_name}.",
                    extra=core_logger.context(console=True),
                )
        import_dict["import_ISO_time"] = import_initiated_time
    else:
        import_dict["imported"] = True
        import_dict["import_source"] = "Basic bulk import"
        import_dict["import_ISO_time"] = import_initiated_time
    return import_dict


def apply_bulk_import_metadata(
    activity: activities_contracts.ActivityCore,  # A parsed activity about to be added to Endurain
    activity_metadata_dict: dict,  # A dictionary containing parsed information from a Strava activities.csv file
) -> None:
    """
    Function adds metadata to a parsed activity that is about to be imported via the bulk ingestion entry.

    The function's primary purpose (i.e., why it was created) is to add metadata from a Strava activities.csv file to a parsed activity file from a Strava bulk import activity that is about to be imported.

    But this function also adds the import_info dictionary metadata to all generic bulk import activities, so it is called in all cases during a bulk import.

    The activity_metadata_dict is originally formed by the build_metadata_dict function, so see that function for contents / keys / etc.

    The function presumes that anything stored in the activities.csv file takes preference over contents of the parsed activity file.  This could be changed in the future (possibly a target for a user-selected option?)
        This decision was made becuase Joao's sample .fit files still contain a very generic title in the .fit files, but had a much more detailed name in Strava.
        # Code to give preference to items in the parsed activity file, should we ever want such a thing:
        #    if activity.name is None and activity_metadata_dict.get("name"):
        #    if activity.description is None and activity_metadata_dict.get("description"):
        #    if activity.gear_id is None and activity_metadata_dict.get("gear_id"):
        #    if activity.import_info is None and activity_metadata_dict.get("import_dict"):
    Note that basic bulk imports will not have many of these field names in activity_metadata_dict, so ensure that they are checked for existence before value checking.

    Mutates the activity in place.
    """
    logger.debug(
        "Applying Strava bulk-import metadata to a parsed activity",
        extra=core_logger.context(fields=sorted(activity_metadata_dict)),
    )
    applied = []
    if activity_metadata_dict.get("name"):
        activity.name = activity_metadata_dict["name"]
        applied.append("name")
    if activity_metadata_dict.get("description"):
        activity.description = activity_metadata_dict["description"]
        applied.append("description")
    if activity_metadata_dict.get("gear_id"):
        activity.gear_id = activity_metadata_dict["gear_id"]
        applied.append("gear_id")
    if activity_metadata_dict.get("import_dict"):
        activity.import_info = activity_metadata_dict["import_dict"]
        applied.append("import_info")
    logger.debug(
        "Applied Strava bulk-import metadata",
        extra=core_logger.context(applied=applied),
    )


def does_activity_start_time_match_the_data_in_strava_activities_csv(
    activity: activities_contracts.ActivityCore,  # A parsed activity about to be added to Endurain
    activity_metadata_dict: dict,  # A dictionary containing parsed information from a Strava activities.csv file
) -> bool:
    """
    Strava includes each multi-activity .fit file once for each activity inside the fit file.  Thus, run without filtering, a 5-activity fit file is imported 5 times for 25 activities imported.

    So, to find out which activity goes with which file, we check if start time of activity aligns with start time of the activity's strava activities.csv file data.  If it does import.

    Formatting of times in the two files:
        Activity start time - from Endurain activity parser: 2023-10-21T07:41:47
        Activity start time - from Strava activities.csv: Oct 21, 2023, 8:13:28 AM

    Returns: True if the start times match.  False if they do not.
    """
    # ``ActivityCore`` normalizes start_time to an aware UTC datetime at
    # construction, but accepts a string — go through the shared coercion rather
    # than assuming either. Parsing this as a string unconditionally raised
    # TypeError once the contract started coercing, which failed the whole file
    # and sent every multi-activity .fit in a Strava export to the error dir.
    endurain_parsed_file_start_date = core_timezone.to_utc_aware(activity.start_time)
    if endurain_parsed_file_start_date is None:
        return False
    strava_csv_start_date = datetime.strptime(activity_metadata_dict["activity date"], "%b %d, %Y, %-I:%-M:%-S %p")
    # Ensure both are tz-aware (or both naive) for comparison
    if strava_csv_start_date.tzinfo is None:
        strava_csv_start_date = strava_csv_start_date.replace(tzinfo=UTC)
    return endurain_parsed_file_start_date == strava_csv_start_date


def import_media_from_strava_bulk_export(
    strava_activities: dict,
    created_activity: activities_schema.Activity,
    file_base_name: str,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """
    Import media files associated with a Strava bulk export activity.

    Reads the pipe-separated media list from the Strava
    activities.csv entry for the given file, then creates
    activity media records for each referenced media file
    found in the Strava bulk import media directory.

    Args:
        strava_activities: Strava bulk-import metadata dict
            keyed by filename, then by activities.csv column
            header.
        created_activity: The newly created activity object
            to which media will be attached.
        file_base_name: Base filename of the activity file,
            used as the lookup key in strava_activities.
        db: SQLAlchemy database session.

    Returns:
        None
    """
    if created_activity.id is None:
        logger.warning(
            f"Bulk file import: cannot import media for {file_base_name} - created activity has no id",
            extra=core_logger.context(console=True),
        )
        return
    if strava_activities.get(file_base_name):
        media_string = strava_activities[file_base_name]["Media"].strip()
        media_list = []
        if media_string is None or not media_string:
            logger.info(
                f"Bulk file import: Media import section - no media list in activities.csv for {file_base_name}",
                extra=core_logger.context(console=True),
            )
        else:
            media_list = media_string.split("|")
            for media_item in media_list:
                strava_media_dir = core_config.STRAVA_BULK_IMPORT_MEDIA_DIR
                _, media_file_base_name = os.path.split(media_item)
                media_path = os.path.join(strava_media_dir, media_file_base_name)
                create_activity_media_from_strava_bulk_import(
                    created_activity.id,
                    media_file_base_name,
                    media_path,
                    db,
                )


def create_activity_media_from_strava_bulk_import(
    activity_id: int,
    media_strava_filename: str,
    media_path_from_strava: str,
    db: Session,
):
    """
    Imports a media file that is attached to an activity that has just been imported via the Strava bulk import routines.

    Note that the imported activity must be created before this function is called, as the activity_id must be known for media import to be successful.

    Returns: nothing
    """

    logger.debug(
        f"Media import: Beginning processing of {media_path_from_strava}", extra=core_logger.context(console=True)
    )
    try:
        # Ensure the 'data/activity_media' directory exists
        final_media_dir = core_config.settings.ACTIVITY_MEDIA_DIR
        os.makedirs(final_media_dir, exist_ok=True)

        # Create new file name and new file path
        new_file_name = f"{activity_id}_{media_strava_filename}"
        new_file_path = os.path.join(final_media_dir, new_file_name)

        if os.path.exists(media_path_from_strava):
            # Validate the media file as an image through the unified
            # pipeline before relocating it into ACTIVITY_MEDIA_DIR
            # (which is served back to clients via FileResponse).
            try:
                file_uploads.validate_local_file_sync(
                    media_path_from_strava,
                    kind=file_uploads.UploadKind.IMAGE,
                    filename=media_strava_filename,
                )
            except HTTPException as err:
                logger.warning(
                    f"Bulk file import media import: Rejecting "
                    f"{media_path_from_strava} - failed image "
                    f"validation: {err.detail}",
                    extra=core_logger.context(console=True),
                )
                return

            file_uploads.move_within(
                media_path_from_strava,
                final_media_dir,
                filename=new_file_name,
                src_base_dir=core_config.STRAVA_BULK_IMPORT_MEDIA_DIR,
            )

            # Add media file to db
            activity_media_crud.create_activity_media(activity_id, new_file_path, db)
            logger.info(
                f"Bulk file import media import: Media file {media_strava_filename} has been imported to db.",
                extra=core_logger.context(console=True),
            )
        else:
            logger.warning(
                f"Bulk file import media import warning: Media file {media_strava_filename} does not exist, skipping import of it - {media_path_from_strava}",
                extra=core_logger.context(console=True),
            )
            return
    except Exception as err:
        logger.error(
            f"Bulk file import media import: Error during processing of {media_path_from_strava}: {err}",
            extra=core_logger.context(console=True),
        )
