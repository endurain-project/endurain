"""Typed contribution contracts for activity ingestion and profile transfer."""

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

import modules.activities.activity.schema as activity_schema


class PersistActivityComponent(Protocol):
    """Persist one parsed component for a newly created activity."""

    def __call__(
        self,
        data: Any,
        activity: activity_schema.Activity,
        db: Session,
        *,
        commit: bool,
    ) -> None: ...


class PersistFileComponent(Protocol):
    """Persist one file-scoped parsed component."""

    def __call__(self, data: Any, db: Session) -> None: ...


class ExportActivityRecords(Protocol):
    """Export profile records scoped to activity identifiers."""

    def __call__(self, activity_ids: list[int], db: Session) -> list[Any]: ...


class RestoreActivityRecords(Protocol):
    """Restore profile records for one remapped activity."""

    def __call__(
        self,
        records: list[dict[str, Any]],
        original_activity_id: int,
        new_activity: activity_schema.Activity,
        db: Session,
    ) -> int: ...


class ExportGlobalRecords(Protocol):
    """Export file-global profile records."""

    def __call__(self, db: Session) -> list[Any]: ...


class RestoreGlobalRecords(Protocol):
    """Restore file-global profile records."""

    def __call__(self, records: list[dict[str, Any]], db: Session) -> int: ...


class ThumbnailUrlResolver(Protocol):
    """Resolve an activity's stored thumbnail key to a servable URL."""

    def __call__(self, key: str | None, activity_id: int) -> str | None: ...


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
