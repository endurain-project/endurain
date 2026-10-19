"""Typed contribution contracts for activity ingestion and profile transfer.

Also holds the two factories for the children that are plain rows hanging off one
activity (laps, sets, workout steps). They differ only in the CRUD write, the
archive names and how one archived record becomes a stored row; the parent-id
guard and the re-keying filter live here once.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

import modules.activities.activity.schema as activity_schema


class PersistActivityComponent(Protocol):
    """Stage one parsed component for a newly created activity.

    The caller owns the transaction: ingestion commits the activity, its
    components and the outbox row together.
    """

    def __call__(
        self,
        data: Any,
        activity: activity_schema.ActivityRead,
        db: Session,
    ) -> None:
        """Stage the component for a newly created activity.

        Args:
            data: The parsed component payload.
            activity: The newly created activity.
            db: Database session.
        """


class PersistFileComponent(Protocol):
    """Persist one file-scoped parsed component."""

    def __call__(self, data: Any, db: Session) -> None:
        """Persist the file-scoped component.

        Args:
            data: The parsed component payload.
            db: Database session.
        """


class ExportActivityRecords(Protocol):
    """Export profile records scoped to activity identifiers."""

    def __call__(self, activity_ids: list[int], db: Session) -> list[Any]:
        """Return the records for the given activities.

        Args:
            activity_ids: IDs of the activities to export.
            db: Database session.

        Returns:
            The records to export.
        """


class RestoreActivityRecords(Protocol):
    """Restore profile records for one remapped activity."""

    def __call__(
        self,
        records: list[dict[str, Any]],
        original_activity_id: int,
        new_activity: activity_schema.ActivityRead,
        db: Session,
    ) -> int:
        """Restore the records onto a remapped activity.

        Args:
            records: Profile records to restore.
            original_activity_id: The activity's ID in the exported archive.
            new_activity: The activity the records are restored onto.
            db: Database session.

        Returns:
            The number of records restored.
        """


class ExportGlobalRecords(Protocol):
    """Export file-global profile records."""

    def __call__(self, db: Session) -> list[Any]:
        """Return the file-global records.

        Args:
            db: Database session.

        Returns:
            The records to export.
        """


class RestoreGlobalRecords(Protocol):
    """Restore file-global profile records."""

    def __call__(self, records: list[dict[str, Any]], db: Session) -> int:
        """Restore the file-global records.

        Args:
            records: Profile records to restore.
            db: Database session.

        Returns:
            The number of records restored.
        """


class ThumbnailUrlResolver(Protocol):
    """Resolve an activity's stored thumbnail key to a servable URL."""

    def __call__(self, key: str | None, activity_id: int) -> str | None:
        """Return the servable URL for a thumbnail key.

        Args:
            key: The stored thumbnail key, or None.
            activity_id: ID of the activity.

        Returns:
            The URL, or None when there is no thumbnail.
        """


@dataclass(frozen=True, slots=True)
class ActivityIngestionContributor:
    """Package contribution for one parsed activity component."""

    key: str
    persist: PersistActivityComponent


@dataclass(frozen=True, slots=True)
class FileIngestionContributor:
    """Package contribution for one file-scoped parsed component."""

    key: str
    persist: PersistFileComponent


@dataclass(frozen=True, slots=True)
class ProfileActivityContributor:
    """Package contribution for activity-scoped profile JSON records."""

    key: str
    archive_path: str
    count_key: str
    split: bool
    export: ExportActivityRecords
    restore: RestoreActivityRecords


@dataclass(frozen=True, slots=True)
class ProfileGlobalContributor:
    """Package contribution for file-global profile JSON records."""

    key: str
    archive_path: str
    count_key: str
    export: ExportGlobalRecords
    restore: RestoreGlobalRecords


class StoreChildRecords[R](Protocol):
    """Stage rows of type ``R`` for one activity through the child package's CRUD."""

    def __call__(self, records: R, activity_id: int, db: Session, /) -> None:
        """Stage the rows for the activity.

        Args:
            records: The parsed or restored rows.
            activity_id: ID of the parent activity.
            db: Database session.
        """


class ParseChildRecord[R](Protocol):
    """Turn one archived profile record into a row of type ``R``."""

    def __call__(self, record: dict[str, Any], activity_id: int, /) -> R:
        """Validate one archived record for a restored activity.

        Args:
            record: The archived record, without its ``id``.
            activity_id: ID of the activity the record is restored onto.

        Returns:
            The value to hand to the store.
        """


def child_ingestion_contributor(
    *,
    key: str,
    store: StoreChildRecords[Any],
) -> ActivityIngestionContributor:
    """Build the ingestion contribution for a plain child collection.

    Args:
        key: The parsed component key the contribution persists.
        store: Stages the parsed rows for an activity.

    Returns:
        The contributor.
    """

    def persist(data: Any, activity: activity_schema.ActivityRead, db: Session) -> None:
        store(data, activity.id, db)

    return ActivityIngestionContributor(key=key, persist=persist)


def child_profile_contributor[R](
    *,
    key: str,
    archive_path: str,
    count_key: str,
    split: bool,
    export: ExportActivityRecords,
    store: StoreChildRecords[list[R]],
    parse_record: ParseChildRecord[R],
) -> ProfileActivityContributor:
    """Build the profile contribution for a plain child collection.

    Restoring keeps only the records that belonged to the original activity,
    drops their archived ``id`` and re-keys them onto the restored activity,
    without mutating the archive's records.

    Args:
        key: The contribution key.
        archive_path: The member of the profile archive that holds the records.
        count_key: The key the restored count is reported under.
        split: Whether the archive stores one file per activity.
        export: Reads the rows for the given activities.
        store: Stages the restored rows for an activity.
        parse_record: Validates one archived record for the restored activity.

    Returns:
        The contributor.
    """

    def restore(
        records: list[dict[str, Any]],
        original_activity_id: int,
        new_activity: activity_schema.ActivityRead,
        db: Session,
    ) -> int:
        restored: list[R] = []
        for record in records:
            if record.get("activity_id") != original_activity_id:
                continue
            data = dict(record)
            data.pop("id", None)
            restored.append(parse_record(data, new_activity.id))
        if restored:
            store(restored, new_activity.id, db)
        return len(restored)

    return ProfileActivityContributor(
        key=key,
        archive_path=archive_path,
        count_key=count_key,
        split=split,
        export=export,
        restore=restore,
    )
