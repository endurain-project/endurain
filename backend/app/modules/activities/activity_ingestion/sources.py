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

:class:`BulkImportSource` is the **extension point**, not a Strava switch. It used
to answer its own questions by calling ``modules.strava.bulk_import_utils``,
which made activities depend on a provider that already depends on activities.
A provider now *subclasses* it (``modules.strava.bulk_import_source``), so the
dependency runs one way and adding a second export format means adding a subclass
rather than another branch in here.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.schema as activities_schema

logger = core_logger.get_logger(__name__)


def build_import_record(import_initiated_time: str, source_label: str = "Basic bulk import") -> dict[str, Any]:
    """Build the ``import_info`` record stamped on every bulk-imported activity.

    Args:
        import_initiated_time: ISO timestamp of when the import run started.
        source_label: Human-readable origin recorded on the activity.

    Returns:
        The import record.
    """
    return {
        "imported": True,
        "import_source": source_label,
        "import_ISO_time": import_initiated_time,
    }


def apply_bulk_import_metadata(
    activity: activities_contracts.ActivityCore,
    activity_metadata: dict,
) -> None:
    """Apply a bulk import's supplemental metadata to a parsed activity, in place.

    The metadata dict is the contract between a source's ``metadata_for`` and
    this function, so a provider subclass supplies richer values without needing
    its own applier. Anything the manifest supplies wins over what the file
    itself parsed to: an export's manifest generally carries the name and gear the
    athlete actually curated, while the file holds whatever the device wrote.

    Args:
        activity: The parsed activity to enrich (mutated in place).
        activity_metadata: Metadata from the source's ``metadata_for``.

    Returns:
        None.
    """
    applied = []
    if activity_metadata.get("name"):
        activity.name = activity_metadata["name"]
        applied.append("name")
    if activity_metadata.get("description"):
        activity.description = activity_metadata["description"]
        applied.append("description")
    if activity_metadata.get("gear_id"):
        activity.gear_id = activity_metadata["gear_id"]
        applied.append("gear_id")
    if activity_metadata.get("import_dict"):
        activity.import_info = activity_metadata["import_dict"]
        applied.append("import_info")
    logger.debug(
        "Applied bulk-import metadata to a parsed activity",
        extra=core_logger.context(applied=applied),
    )


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
        gear_id: Internal gear id the Garmin sync already resolved from the
            activity's synced gear, when the athlete has gear sync enabled.
            Resolved provider-side so ingestion never has to ask a provider
            module anything.
        provider_gear_id: The Garmin Connect gear UUID, recorded on the activity.
        activity_name: Optional override for the parsed activity's name.
    """

    gear_id: int | None = None
    provider_gear_id: str | None = None
    activity_name: str | None = None

    kind = "garmin"


@dataclass(frozen=True)
class BulkImportSource:
    """A file from a bulk import of a folder the athlete dropped in.

    Also the base a provider export subclasses when its files come with a
    manifest, sidecar media, or duplicate listings to skip. The four hooks below
    are the only things such an export can change.

    Attributes:
        import_initiated_time: ISO timestamp of when the import run started,
            recorded on each imported activity.
        user_id: Owner of the import, used to resolve that user's error
            directory. ``None`` when the import has its own shared directory.
    """

    import_initiated_time: str | None = None
    user_id: int | None = None

    kind = "bulk_import"

    @property
    def error_directory(self) -> str:
        """Directory a file is moved to when its import fails.

        Per-user for a generic bulk import, matching the per-user drop
        directory: moving one user's failed file into a shared location would
        undo the isolation the import itself enforces.
        """
        if self.user_id is None:
            return core_config.FILES_BULK_IMPORT_IMPORT_ERRORS_DIR
        return core_config.bulk_import_error_dir_for(self.user_id)

    def metadata_for(self, file_base_name: str) -> dict:
        """Build the supplemental metadata to apply to activities from one file.

        Args:
            file_base_name: The original (pre-decompression) base filename, which
                is a manifest lookup key for the sources that have one.

        Returns:
            The metadata dict, empty when there is nothing to apply.
        """
        if not self.import_initiated_time:
            return {}
        return {"import_dict": build_import_record(self.import_initiated_time)}

    def should_import(
        self,
        activity: activities_contracts.ActivityCore,
        activity_metadata: dict,
        *,
        activities_in_file: int,
    ) -> bool:
        """Whether one activity parsed from a multi-activity file should be imported.

        Args:
            activity: The parsed activity under consideration.
            activity_metadata: Metadata from :meth:`metadata_for`.
            activities_in_file: How many activities the file yielded.

        Returns:
            ``True`` to import. A plain folder import has no manifest listing the
            same file once per activity, so nothing is a duplicate.
        """
        return True

    def apply_metadata(
        self,
        activity: activities_contracts.ActivityCore,
        activity_metadata: dict,
    ) -> None:
        """Apply this import's supplemental metadata to a parsed activity, in place.

        Args:
            activity: The parsed activity to enrich, mutated in place.
            activity_metadata: Metadata from :meth:`metadata_for`.

        Returns:
            None.
        """
        apply_bulk_import_metadata(activity, activity_metadata)

    def import_side_artifacts(
        self,
        created_activities: list[activities_schema.Activity],
        file_base_name: str,
        db: Session,
    ) -> None:
        """Import anything that travelled alongside the file rather than inside it.

        A plain folder import has no sidecar, so this is a no-op; a provider
        export overrides it. The pipeline calls it without knowing which kind of
        import it is running.

        Args:
            created_activities: Activities persisted from the file, in order.
            file_base_name: The file's original base name.
            db: Database session.

        Returns:
            None.
        """
        return None


#: Any of the three things that can feed the ingestion pipeline.
IngestionSource = UploadSource | GarminSource | BulkImportSource
