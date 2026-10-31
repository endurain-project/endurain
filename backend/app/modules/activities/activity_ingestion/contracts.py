"""What an activity file came from — the ingestion pipeline's source context.

Ingestion is one pipeline fed by three different callers. Each passes exactly
one of the source objects below, so an illegal combination of flags cannot be
expressed, and the questions the pipeline asks ("where do failed files go?",
"what metadata applies to this file?") are answered by the source itself.

:class:`BulkImportSource` is the **extension point**, not a Strava switch. A
provider *subclasses* it (``modules.strava.bulk_import_source``), so the
dependency runs one way, from provider to activities, and adding a second export
format means adding a subclass rather than another branch in here.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.schema as activity_schema

#: Fetch a user's activities recorded in ``[window_start, window_end]``, storing
#: each through the ingestion seam and returning what it stored. Returns an empty
#: list (or ``None``) when the user has not linked this provider — an unlinked
#: integration is not an error.
#:
#: Synchronous and session-less: it runs on a worker thread, and the provider
#: opens a short session per unit of work so no transaction is held open across
#: a network call.
FetchWindow = Callable[
    [int, datetime, datetime],
    list[activity_schema.ActivityRead] | None,
]

#: The ids of users who have linked this provider, ascending, those greater than
#: ``after_id``, at most ``limit``. Lets the scheduler enqueue one refresh per
#: linked user instead of walking every user.
LinkedUserIds = Callable[[int, int], list[int]]


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
    activity: activity_contracts.ActivityCore,
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
    """
    if activity_metadata.get("name"):
        activity.name = activity_metadata["name"]
    if activity_metadata.get("description"):
        activity.description = activity_metadata["description"]
    if activity_metadata.get("gear_id"):
        activity.gear_id = activity_metadata["gear_id"]
    if activity_metadata.get("import_dict"):
        activity.import_info = activity_metadata["import_dict"]


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
        user_id: Owner of the import.
    """

    import_initiated_time: str | None = None
    user_id: int | None = None

    kind = "bulk_import"

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
        activity: activity_contracts.ActivityCore,
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
        activity: activity_contracts.ActivityCore,
        activity_metadata: dict,
    ) -> None:
        """Apply this import's supplemental metadata to a parsed activity, in place.

        Args:
            activity: The parsed activity to enrich, mutated in place.
            activity_metadata: Metadata from :meth:`metadata_for`.
        """
        apply_bulk_import_metadata(activity, activity_metadata)

    def import_side_artifacts(
        self,
        created_activities: list[activity_schema.ActivityRead],
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
        """
        return None


#: Any of the three things that can feed the ingestion pipeline.
IngestionSource = UploadSource | GarminSource | BulkImportSource


#: Read one member of the archive being imported, by name, or ``None`` when it is
#: not in the archive. Lets a provider export reach its manifest and sidecar media
#: without knowing where the archive is stored.
ArchiveMemberReader = Callable[[str], bytes | None]


@dataclass(frozen=True)
class BulkImportFormat:
    """How one kind of bulk-import archive is laid out and interpreted.

    The generic format is built in. A provider whose export carries a manifest or
    sidecar media registers its own, so ingestion learns the layout without
    importing the provider.

    Attributes:
        name: Stable identifier, the ``import_source`` clients select.
        is_activity_member: Whether an archive member (``/``-separated path) is an
            activity file to import.
        is_export_member: Whether a file in the drop folder belongs to the export
            (activity files plus a manifest and sidecar media). Only these are
            packed and consumed; anything else in the folder is left alone.
        drop_directory: The directory a user places this export's files in for the
            server-side import, for a given user id.
        build_source: Builds the source applied to every file of one batch from
            ``(user_id, import_initiated_time, read_member)``. May raise a domain
            error when the archive is not a valid export of this format.
    """

    name: str
    is_activity_member: Callable[[str], bool]
    is_export_member: Callable[[str], bool]
    drop_directory: Callable[[int], str]
    build_source: Callable[[int, str, ArchiveMemberReader], BulkImportSource]


@dataclass(frozen=True)
class BulkImportState:
    """What a batch needs to know about a bulk-import job before it starts.

    Attributes:
        user_id: Owner of the import.
        import_source: The format name.
        staged_key: Key of the staged archive, or ``None`` while it is still being
            assembled (or once the job is finished).
        cursor: Last member handled, or ``None`` at the start.
        files_total: Importable files in the archive.
        files_done: Files imported so far.
        files_failed: Files that could not be imported.
        created_at: When the import was requested.
        finished: Whether the job already reached a terminal state.
    """

    user_id: int
    import_source: str
    staged_key: str | None
    cursor: str | None
    files_total: int
    files_done: int
    files_failed: int
    created_at: datetime
    finished: bool
