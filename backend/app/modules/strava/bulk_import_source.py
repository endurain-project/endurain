"""The Strava-export specialisation of the bulk-import source.

A Strava export is a folder of activity files plus an ``activities.csv`` manifest
and a ``media`` directory. Three things follow from that, and all three are facts
about Strava rather than about bulk import:

* the manifest supplies names, descriptions and gear the exported files omit,
* it lists a multi-activity ``.fit`` once per activity inside it, so importing
  every activity from every listing multiplies them (a 5-activity file becomes
  25),
* the photos ship next to the files rather than inside them.

Answering those used to be ``BulkImportSource``'s job in the activities module,
which meant activities imported ``modules.strava`` while Strava imported the
ingestion entry point — a cycle that pinned the two modules together. Subclassing
here reverses it: Strava knows about activities, activities knows nothing about
Strava.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.sources as ingestion_sources
import modules.strava.bulk_import_utils as strava_bulk_import_utils

logger = core_logger.get_logger(__name__)


@dataclass(frozen=True)
class StravaBulkImportSource(ingestion_sources.BulkImportSource):
    """A file from a Strava bulk export.

    Attributes:
        strava_activities: Parsed Strava ``activities.csv``, keyed by filename.
        gear_nickname_to_id: Gear nickname -> internal gear id, used to resolve
            the gear named in the CSV.
    """

    strava_activities: dict | None = None
    gear_nickname_to_id: dict | None = None

    @property
    def error_directory(self) -> str:
        """Directory a file is moved to when its import fails.

        A Strava export lands in one shared directory rather than a per-user
        drop, so its failures do too.
        """
        return core_config.STRAVA_BULK_IMPORT_IMPORT_ERRORS_DIR

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
        activity: activities_contracts.ActivityCore,
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
            "Bulk activity import of multi-activity .fit file: "
            "skipping likely duplicate import. "
            "Start time does not align with start time for this .fit file "
            "in the Strava activities.csv file.",
            extra=core_logger.context(console=True),
        )
        return False

    def import_side_artifacts(
        self,
        created_activities: list[activities_schema.Activity],
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

        Returns:
            None.
        """
        if not self.strava_activities or not created_activities:
            return
        strava_bulk_import_utils.import_media_from_strava_bulk_export(
            self.strava_activities,
            created_activities[-1],
            file_base_name,
            db,
        )
