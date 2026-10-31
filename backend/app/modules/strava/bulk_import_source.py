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
from dataclasses import dataclass

from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.strava.bulk_import_utils as strava_bulk_import_utils
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)

FORMAT_NAME = "strava"

_ACTIVITIES_FOLDER = "activities"


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
        return strava_bulk_import_utils.build_metadata_dict(
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
        if strava_bulk_import_utils.does_activity_start_time_match_the_data_in_strava_activities_csv(
            activity, activity_metadata
        ):
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
        strava_bulk_import_utils.import_media_from_strava_bulk_export(
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
        or (top == strava_bulk_import_utils.MEDIA_FOLDER and "/" in member_name)
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
        strava_activities = strava_bulk_import_utils.parse_activities_manifest(path)
    if strava_activities is None:
        raise core_exceptions.InvalidInputError("The export's activities.csv could not be read")

    with SessionLocal() as db:
        gear = strava_bulk_import_utils.create_gear_dictionary_for_bulk_import(user_id, db)

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
            name=FORMAT_NAME,
            is_activity_member=_is_activity_member,
            is_export_member=_is_export_member,
            drop_directory=core_config.strava_bulk_import_dir_for,
            build_source=_build_source,
        )
    )
