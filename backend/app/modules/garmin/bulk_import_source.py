"""The Garmin-export specialisation of the bulk-import source, and its archive layout.

A Garmin GDPR export holds the activity files plus ``*_summarizedActivities.json``
files listing each activity's Garmin Connect name and start time. The FIT files
themselves only carry a generic workout name ("Workout"), so this source names
each imported activity from the summary entry with the same start time, as the
Garmin Connect sync would.
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass, field

import core.config as core_config
import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.garmin.bulk_import_utils as garmin_bulk_import_utils

FORMAT_NAME = "garmin"


@dataclass(frozen=True)
class GarminBulkImportSource(activity_ingestion_integration.BulkImportSource):
    """A file from a Garmin bulk export.

    Attributes:
        activity_names: Garmin Connect activity names keyed by start time as
            epoch seconds, from the export's summary files.
    """

    activity_names: dict[int, str | None] = field(default_factory=dict)

    import_source_label = "Garmin bulk import"

    def apply_metadata(
        self,
        activity: activity_contracts.ActivityCore,
        activity_metadata: dict,
    ) -> None:
        """Apply the import record, then the Garmin Connect name matching the start time.

        Args:
            activity: The parsed activity to enrich, mutated in place.
            activity_metadata: Metadata from :meth:`metadata_for`.
        """
        super().apply_metadata(activity, activity_metadata)
        name = garmin_bulk_import_utils.find_name_for_start_time(self.activity_names, activity.start_time)
        if name:
            activity.name = name


def _is_activity_member(member_name: str) -> bool:
    """Whether an archive member is an activity file of a Garmin export.

    Args:
        member_name: The member's path inside the archive.

    Returns:
        True for a file with a supported extension, in any folder, that is not OS metadata.
    """
    base = os.path.basename(member_name)
    if not base or base.startswith(".") or member_name.startswith("__MACOSX/"):
        return False
    return os.path.splitext(base)[1].lower() in core_config.SUPPORTED_FILE_FORMATS


def _is_export_member(member_name: str) -> bool:
    """Whether a file in the drop folder belongs to a Garmin export.

    Args:
        member_name: The file's path relative to the folder.

    Returns:
        True for an activity file or a summary file.
    """
    return _is_activity_member(member_name) or garmin_bulk_import_utils.is_summary_member(member_name)


def _build_source(
    user_id: int,
    import_initiated_time: str,
    read_member: activity_ingestion_integration.ArchiveMemberReader,
    member_names: Sequence[str],
) -> GarminBulkImportSource:
    """Build the source for one batch from the export's summary files.

    Args:
        user_id: The importing user.
        import_initiated_time: ISO timestamp of when the import began.
        read_member: Reads a member of the archive by name.
        member_names: Every member path in the archive.

    Returns:
        The source applied to every file of the batch.

    Raises:
        InvalidInputError: When the archive has no ``summarizedActivities.json`` file.
    """
    if not any(garmin_bulk_import_utils.is_summary_member(name) for name in member_names):
        raise core_exceptions.InvalidInputError("The export has no summarizedActivities.json")
    return GarminBulkImportSource(
        import_initiated_time=import_initiated_time,
        user_id=user_id,
        activity_names=garmin_bulk_import_utils.load_summarized_activities(member_names, read_member),
    )


def register_bulk_import_format() -> None:
    """Register the Garmin export layout with activity ingestion."""
    activity_ingestion_integration.register_bulk_import_format(
        activity_ingestion_integration.BulkImportFormat(
            name=FORMAT_NAME,
            is_activity_member=_is_activity_member,
            is_export_member=_is_export_member,
            drop_directory=core_config.bulk_import_dir_for,
            build_source=_build_source,
        )
    )
