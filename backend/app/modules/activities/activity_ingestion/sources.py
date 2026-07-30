"""What an activity file came from — the ingestion pipeline's source context.

Ingestion is one pipeline fed by three different callers, and the differences
between them used to travel as six loosely-related keyword arguments
(``from_garmin``, ``is_bulk_import``, ``garminconnect_gear``,
``strava_activities``, ``import_initiated_time``,
``users_existing_gear_nickname_to_id``) threaded through every layer. Most
combinations of those were meaningless — ``from_garmin=True`` together with
``strava_activities`` describes nothing — and each layer re-derived the same
conclusions from them.

Each caller now passes exactly one of the source objects below, so the illegal
combinations cannot be expressed, and the questions the pipeline actually asks
("where do failed files go?", "what metadata applies to this file?") are answered
by the source itself instead of by re-reading the flags.
"""

from dataclasses import dataclass

import core.config as core_config
import core.logger as core_logger
import modules.activities.activity.contracts as activities_contracts
import modules.strava.bulk_import_utils as strava_bulk_import_utils

logger = core_logger.get_logger(__name__)


@dataclass(frozen=True)
class UploadSource:
    """A file uploaded directly by the athlete through the API."""

    #: Optional override for the parsed activity's name.
    activity_name: str | None = None

    kind = "upload"


@dataclass(frozen=True)
class GarminSource:
    """A file downloaded by the Garmin Connect sync.

    Garmin activities carry a provider id, so they are deduplicated on that
    rather than on a file content hash.

    Attributes:
        gear: Garmin Connect gear metadata (``[{"uuid": ...}, ...]``) to associate
            with the imported activity, when the athlete has gear sync enabled.
        activity_name: Optional override for the parsed activity's name.
    """

    gear: dict | None = None
    activity_name: str | None = None

    kind = "garmin"


@dataclass(frozen=True)
class BulkImportSource:
    """A file from a bulk import — either a generic folder or a Strava export.

    A Strava export is distinguished by carrying ``strava_activities``: the
    parsed ``activities.csv`` keyed by filename, which supplies names,
    descriptions and gear that the exported files themselves do not contain.

    Attributes:
        import_initiated_time: ISO timestamp of when the import run started,
            recorded on each imported activity.
        strava_activities: Parsed Strava ``activities.csv``, keyed by filename.
            ``None`` for a generic bulk import.
        gear_nickname_to_id: Gear nickname -> internal gear id, used to resolve
            the gear named in the Strava CSV.
    """

    import_initiated_time: str | None = None
    strava_activities: dict | None = None
    gear_nickname_to_id: dict | None = None

    kind = "bulk_import"

    @property
    def is_strava(self) -> bool:
        """Whether this import is a Strava bulk export rather than a generic one."""
        return bool(self.strava_activities) and isinstance(self.strava_activities, dict)

    @property
    def error_directory(self) -> str:
        """Directory a file is moved to when its import fails."""
        return (
            core_config.STRAVA_BULK_IMPORT_IMPORT_ERRORS_DIR
            if self.strava_activities
            else core_config.FILES_BULK_IMPORT_IMPORT_ERRORS_DIR
        )

    def metadata_for(self, file_base_name: str) -> dict:
        """Build the supplemental metadata to apply to activities from one file.

        For a Strava export this is the matching ``activities.csv`` row (name,
        description, gear, plus the import record); for a generic bulk import it
        is just the import record.

        Args:
            file_base_name: The original (pre-decompression) base filename, which
                is the key into the Strava ``activities.csv`` data.

        Returns:
            The metadata dict, empty when there is nothing to apply.
        """
        if not self.import_initiated_time:
            return {}
        if self.is_strava:
            return strava_bulk_import_utils.build_metadata_dict(
                file_base_name,
                self.strava_activities,
                self.import_initiated_time,
                self.gear_nickname_to_id,
            )
        return {
            "import_dict": strava_bulk_import_utils.build_import_dictionary(
                file_base_name, self.import_initiated_time, False
            )
        }

    def should_import(
        self,
        activity: activities_contracts.ActivityCore,
        activity_metadata: dict,
        *,
        activities_in_file: int,
    ) -> bool:
        """Whether one activity parsed from a multi-activity file should be imported.

        A Strava export lists a multi-activity ``.fit`` once per activity it
        contains, so importing every activity from every listing would multiply
        them (a 5-activity file becomes 25). The ``activities.csv`` row identifies
        which one this listing refers to by start time.

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
            "Bulk activity import of multi-activity .fit file: "
            "skipping likely duplicate import. "
            "Start time does not align with start time for this .fit file "
            "in the Strava activities.csv file.",
            extra=core_logger.context(console=True),
        )
        return False


#: Any of the three things that can feed the ingestion pipeline.
IngestionSource = UploadSource | GarminSource | BulkImportSource
