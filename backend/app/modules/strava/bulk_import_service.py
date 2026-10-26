"""The Strava-export specialisation of the bulk-import source, and its archive layout.

A Strava export is a folder of activity files plus an ``activities.csv`` manifest
and a ``media`` directory. Three things follow from that, and all three are facts
about Strava rather than about bulk import:

* the manifest supplies names, descriptions and gear the exported files omit,
* it lists a multi-activity ``.fit`` once per activity inside it, so importing
  every activity from every listing multiplies them (a 5-activity file becomes
  25),
* the photos ship next to the files rather than inside them.

Activities knows nothing about Strava: this module registers a
:class:`BulkImportFormat` that says where the activity files are, where the user
drops them, and how to build the source that answers those three questions.
"""

import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.file_uploads as file_uploads
import core.logger as core_logger
import core.text_imports as core_text_imports
import core.timezone as core_timezone
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_media.integration_service as activity_media_integration
import modules.gears.gear.integration_service as gears_integration
import modules.strava.constants as strava_constants
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)

_ACTIVITIES_FOLDER = "activities"


#: The folder of an export holding the activity photos.
MEDIA_FOLDER = "media"

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


def parse_activities_manifest(manifest_path: str) -> dict | None:
    """Parses a Strava ``activities.csv`` manifest.

    Args:
        manifest_path: Path of the manifest file.

    Returns:
        Dictionary of the manifest's rows keyed by each activity's filename, or
        ``None`` when the file cannot be parsed or lacks the required headers.
    """
    strava_activities_file_name = os.path.basename(manifest_path)
    try:
        strava_activities_dict = {}
        for row in core_text_imports.read_bounded_csv(manifest_path):
            # Check to see if file has headers that will be used during parsing of the file.
            missing_headers = _STRAVA_ACTIVITIES_HEADERS - row.keys()
            if missing_headers:
                logger.error(
                    "Aborting Strava bulk activities import: required headers missing",
                    extra=core_logger.context(
                        console=True, file_name=strava_activities_file_name, missing=sorted(missing_headers)
                    ),
                )
                return None
            _, strava_act_file_name = os.path.split(row["Filename"])  # strips path, returns filename with extension.
            strava_activities_dict[strava_act_file_name] = row
        logger.info(
            "Strava bulk import: activities.csv parsed",
            extra=core_logger.context(console=True, row_count=len(strava_activities_dict)),
        )
        return strava_activities_dict
    except core_exceptions.DomainError as err:
        # ``read_bounded_csv`` raises 413/424 for oversized files or stat/open
        # failures; surface the structured detail instead of a bare ``None``.
        logger.error(
            "Strava activities CSV parsing aborted", extra=core_logger.context(console=True, detail=err.detail)
        )
        return None
    except Exception as err:
        logger.error("Strava activities CSV parsing failed", extra=core_logger.context(console=True, error=str(err)))
        return None


def create_gear_dictionary_for_bulk_import(user_id: int, db: Session) -> dict[str, list[int]]:
    """Creates a dictionary that links gear nicknames in Endurain to their Endurain gear IDs.

    The dictionary includes both base Endurain gear nickname and the gear name smoosh ("{brand} {model} {name}") that Strava uses for its shoe gear listing in activities.csv

    Args:
        user_id: The importing user.
        db: Database session.

    Returns:
        Dictionary that uses the gear name as a key to look up the gear ID; empty
        when the user has no gear, which only means no activity is linked to one.
    """
    gear_by_name: dict[str, list[int]] = {}
    for item in gears_integration.get_gear_user(user_id, db) or []:
        gear_by_name[item.nickname] = [item.id]
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
        gear_by_name.setdefault(strava_name_smoosh, [item.id])
    return gear_by_name


def build_metadata_dict(
    file_base_name: str,  # String with the base filename being processed (also key to strava_activities dictionary)
    strava_activities: dict,  # dictionary with info for a Strava bulk import - format strava_activities["filename"]["column header from Strava activities spreadsheet"]
    import_initiated_time: str,  # String containing the time the Strava bulk import was initiated.
    users_existing_gear_nickname_to_id: dict
    | None = None,  # Dictionary containing gear nickname to ID, needed for Strava bulk import
) -> dict:
    """Creates a dictionary with metadata information pulled from a Strava activities file.

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
                    "Bulk file import: gear named in activities.csv not found, not adding gear to activity",
                    extra=core_logger.context(console=True, file_name=file_base_name, gear=activity_gear),
                )
        else:
            strava_activity_metadata["gear_id"] = None
        import_dict = build_import_dictionary(file_base_name, import_initiated_time, True, strava_activities)
        strava_activity_metadata["import_dict"] = import_dict
        strava_activity_metadata["metadata_found_in_csv"] = True  # We found metadata in the CSV!
        logger.info(
            "Bulk file import: activities.csv metadata extracted",
            extra=core_logger.context(console=True, file_name=file_base_name),
        )
    else:
        # We are in a Strava import, but don't have data on the file.  Just do a basic metadata addition.
        import_dict = build_import_dictionary(file_base_name, import_initiated_time, False)
        strava_activity_metadata["metadata_found_in_csv"] = (
            False  # No metadata found in CSV, so don't try to add it in later.
        )
        strava_activity_metadata["import_dict"] = import_dict

        logger.info(
            "Bulk file import: no data in activities.csv for activity",
            extra=core_logger.context(console=True, file_name=file_base_name),
        )

    return strava_activity_metadata


def build_import_dictionary(
    file_base_name: str,  # String with the base filename being processed (also key to strav_activities dictionary)
    import_initiated_time: str,  # String containing the time the Strava bulk import was initiated.
    is_strava_bulk_import: bool = False,  # Boolean to track if we are doing a Strava bulk import or not
    strava_activities: dict
    | None = None,  # dictionary with info for a Strava bulk import - format strava_activities["filename"]["column header from Strava activities spreadsheet"]
) -> dict:
    """Creates the "import_info" dictionary that is added to all activities that are imported from files.

    Functions both for Strava imports and generic bulk imports, depending on whether the is_strava_bulk_import variable is set or not.

    Returns: Dictionary that contains the import_dict values for the activity (which is then added to the activity as a dictionary in the "import_info" field of the activity).
    """
    import_dict: dict[str, Any] = {}
    if is_strava_bulk_import:
        import_dict = activity_ingestion_integration.build_import_record(import_initiated_time, "Strava bulk import")
        activity_id_value = strava_activities[file_base_name].get("Activity ID", "")
        if activity_id_value:
            try:
                import_dict["strava_activity_id"] = int(activity_id_value)
            except (TypeError, ValueError):
                logger.warning(
                    "Bulk file import: ignoring invalid Strava activity id",
                    extra=core_logger.context(console=True, file_name=file_base_name),
                )
    else:
        import_dict = activity_ingestion_integration.build_import_record(import_initiated_time)
    return import_dict


def does_activity_start_time_match_the_data_in_strava_activities_csv(
    activity: activity_contracts.ActivityCore,  # A parsed activity about to be added to Endurain
    activity_metadata_dict: dict,  # A dictionary containing parsed information from a Strava activities.csv file
) -> bool:
    """Strava includes each multi-activity .fit file once for each activity inside the fit file.  Thus, run without filtering, a 5-activity fit file is imported 5 times for 25 activities imported.

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
    strava_csv_start_date = datetime.strptime(activity_metadata_dict["activity date"], "%b %d, %Y, %I:%M:%S %p")
    # Ensure both are tz-aware (or both naive) for comparison
    if strava_csv_start_date.tzinfo is None:
        strava_csv_start_date = strava_csv_start_date.replace(tzinfo=UTC)
    return endurain_parsed_file_start_date == strava_csv_start_date


def import_media_from_strava_bulk_export(
    strava_activities: dict,
    created_activity: activity_schema.ActivityRead,
    file_base_name: str,
    read_member: Callable[[str], bytes | None],
    db: Session,
) -> None:
    """Import media files associated with a Strava bulk export activity.

    Reads the pipe-separated media list from the Strava ``activities.csv`` entry
    for the given file, then attaches each referenced image found in the export's
    ``media`` folder.

    Args:
        strava_activities: Strava bulk-import metadata dict keyed by filename,
            then by activities.csv column header.
        created_activity: The newly created activity object to which media will
            be attached.
        file_base_name: Base filename of the activity file, used as the lookup key
            in strava_activities.
        read_member: Reads a member of the archive being imported by name.
        db: SQLAlchemy database session.
    """
    if created_activity.id is None:
        logger.warning(
            "Bulk file import: cannot import media, created activity has no id",
            extra=core_logger.context(console=True, file_name=file_base_name),
        )
        return
    row = strava_activities.get(file_base_name)
    if not row:
        return
    media_string = (row.get("Media") or "").strip()
    if not media_string:
        logger.info(
            "Bulk file import: no media list in activities.csv",
            extra=core_logger.context(console=True, file_name=file_base_name),
        )
        return
    for media_item in media_string.split("|"):
        media_file_base_name = os.path.basename(media_item)
        if not media_file_base_name:
            continue
        data = read_member(f"{MEDIA_FOLDER}/{media_file_base_name}")
        if data is None:
            logger.warning(
                "Bulk file import: media file is not in the export, skipping it",
                extra=core_logger.context(console=True, file_name=media_file_base_name),
            )
            continue
        create_activity_media_from_strava_bulk_import(created_activity.id, media_file_base_name, data, db)


def create_activity_media_from_strava_bulk_import(
    activity_id: int,
    media_strava_filename: str,
    data: bytes,
    db: Session,
) -> None:
    """Attaches a media file from a Strava export to an activity that was just imported.

    The bytes are validated as an image through the unified upload pipeline before
    they are stored and become servable; a rejected file is logged and skipped so
    one bad photo does not fail the activity.

    Args:
        activity_id: The imported activity.
        media_strava_filename: The file's name in the export.
        data: The file's bytes.
        db: Database session.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="strava-media-") as work_dir:
            path = os.path.join(work_dir, "media")
            with open(path, "wb") as handle:
                handle.write(data)
            try:
                file_uploads.validate_local_file_sync(
                    path, kind=file_uploads.UploadKind.IMAGE, filename=media_strava_filename
                )
            except core_exceptions.DomainError as err:
                logger.warning(
                    "Bulk file import: rejecting media file that failed image validation",
                    extra=core_logger.context(console=True, file_name=media_strava_filename, detail=err.detail),
                )
                return

        # The media module owns the storage key and area; this only supplies the
        # validated bytes, which keeps the photo reachable on object storage and
        # only through the token-gated route.
        activity_media_integration.attach_media_bytes(activity_id, media_strava_filename, data, db)
        logger.info(
            "Bulk file import: media file imported",
            extra=core_logger.context(console=True, file_name=media_strava_filename),
        )
    except Exception as err:
        logger.error(
            "Bulk file import: error processing media file",
            extra=core_logger.context(console=True, file_name=media_strava_filename, error=str(err)),
        )


@dataclass(frozen=True)
class StravaBulkImportSource(activity_ingestion_integration.BulkImportSource):
    """A file from a Strava bulk export.

    Attributes:
        strava_activities: Parsed Strava ``activities.csv``, keyed by filename.
        gear_nickname_to_id: Gear nickname -> internal gear id, used to resolve
            the gear named in the CSV.
        read_member: Reads a member of the archive by name, to reach the photos.
    """

    strava_activities: dict | None = None
    gear_nickname_to_id: dict | None = None
    read_member: activity_ingestion_integration.ArchiveMemberReader | None = None

    def metadata_for(self, file_base_name: str) -> dict:
        """Build the supplemental metadata from the matching ``activities.csv`` row.

        Args:
            file_base_name: The original (pre-decompression) base filename, which
                is the key into the ``activities.csv`` data.

        Returns:
            The metadata dict, empty when the import carries no start timestamp.
        """
        if not self.import_initiated_time:
            return {}
        if not self.strava_activities:
            return super().metadata_for(file_base_name)
        return build_metadata_dict(
            file_base_name,
            self.strava_activities,
            self.import_initiated_time,
            self.gear_nickname_to_id,
        )

    def should_import(
        self,
        activity: activity_contracts.ActivityCore,
        activity_metadata: dict,
        *,
        activities_in_file: int,
    ) -> bool:
        """Whether one activity parsed from a multi-activity file should be imported.

        The ``activities.csv`` row identifies which activity inside the file this
        listing refers to, by start time; the others are duplicates of listings
        handled elsewhere in the run.

        Args:
            activity: The parsed activity under consideration.
            activity_metadata: Metadata from :meth:`metadata_for`.
            activities_in_file: How many activities the file yielded.

        Returns:
            ``True`` to import, ``False`` to skip as a duplicate listing.
        """
        if activities_in_file <= 1 or not self.strava_activities:
            return True
        if activity_metadata.get("metadata_found_in_csv") is not True:
            return True
        if does_activity_start_time_match_the_data_in_strava_activities_csv(activity, activity_metadata):
            return True
        logger.debug(
            "Bulk activity import of multi-activity .fit file: skipping likely duplicate import. "
            "Start time does not align with start time for this .fit file in the Strava activities.csv file.",
            extra=core_logger.context(console=True),
        )
        return False

    def import_side_artifacts(
        self,
        created_activities: list[activity_schema.ActivityRead],
        file_base_name: str,
        db: Session,
    ) -> None:
        """Attach the photos the export ships alongside the activity file.

        Even a multi-activity ``.fit`` is handled correctly by attaching to the
        last created activity — a Strava export's activity directory holds one
        imported activity per file.

        Args:
            created_activities: Activities persisted from the file, in order.
            file_base_name: The file's original base name (the ``activities.csv``
                lookup key).
            db: Database session.
        """
        if not self.strava_activities or not created_activities or self.read_member is None:
            return
        import_media_from_strava_bulk_export(
            self.strava_activities,
            created_activities[-1],
            file_base_name,
            self.read_member,
            db,
        )


def _is_activity_member(member_name: str) -> bool:
    """Whether an archive member is an activity file of a Strava export.

    Args:
        member_name: The member's path inside the archive.

    Returns:
        True for a supported file directly inside the export's ``activities`` folder.
    """
    base = os.path.basename(member_name)
    folder = os.path.dirname(member_name).split("/")[-1]
    return (
        folder == _ACTIVITIES_FOLDER
        and not base.startswith(".")
        and os.path.splitext(base)[1].lower() in core_config.SUPPORTED_FILE_FORMATS
    )


def _is_export_member(member_name: str) -> bool:
    """Whether a file in the drop folder belongs to a Strava export.

    Args:
        member_name: The file's path relative to the folder.

    Returns:
        True for the manifest, an activity file or a photo.
    """
    top = member_name.split("/", 1)[0]
    return (
        member_name == core_config.STRAVA_BULK_IMPORT_ACTIVITIES_FILE
        or _is_activity_member(member_name)
        or (top == MEDIA_FOLDER and "/" in member_name)
    )


def _build_source(
    user_id: int,
    import_initiated_time: str,
    read_member: activity_ingestion_integration.ArchiveMemberReader,
) -> StravaBulkImportSource:
    """Build the source for one batch from the export's manifest and the user's gear.

    Args:
        user_id: The importing user.
        import_initiated_time: ISO timestamp of when the import began.
        read_member: Reads a member of the archive by name.

    Returns:
        The source applied to every file of the batch.

    Raises:
        InvalidInputError: When the archive has no usable ``activities.csv``.
    """
    manifest = read_member(core_config.STRAVA_BULK_IMPORT_ACTIVITIES_FILE)
    if manifest is None:
        raise core_exceptions.InvalidInputError("The export has no activities.csv")
    with tempfile.TemporaryDirectory(prefix="strava-manifest-") as work_dir:
        path = os.path.join(work_dir, core_config.STRAVA_BULK_IMPORT_ACTIVITIES_FILE)
        with open(path, "wb") as handle:
            handle.write(manifest)
        strava_activities = parse_activities_manifest(path)
    if strava_activities is None:
        raise core_exceptions.InvalidInputError("The export's activities.csv could not be read")

    with SessionLocal() as db:
        gear = create_gear_dictionary_for_bulk_import(user_id, db)

    return StravaBulkImportSource(
        import_initiated_time=import_initiated_time,
        user_id=user_id,
        strava_activities=strava_activities,
        gear_nickname_to_id=gear,
        read_member=read_member,
    )


def register_bulk_import_format() -> None:
    """Register the Strava export layout with activity ingestion."""
    activity_ingestion_integration.register_bulk_import_format(
        activity_ingestion_integration.BulkImportFormat(
            name=strava_constants.BULK_IMPORT_FORMAT_NAME,
            is_activity_member=_is_activity_member,
            is_export_member=_is_export_member,
            drop_directory=core_config.strava_bulk_import_dir_for,
            build_source=_build_source,
        )
    )
