"""Public record and blob operations for activity media."""

from typing import Any

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.service as activity_media_service
import modules.activities.contributors as activities_contributors

logger = core_logger.get_logger(__name__)


def _list_media_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """Return media records for activity IDs already scoped by the caller.

    Args:
        activity_ids: IDs of the activities to read.
        db: Database session.

    Returns:
        Media records for activity IDs already scoped by the caller.
    """
    return activity_media_crud.get_activities_media(activity_ids, db)


def _restore_media_records(
    media: list[activity_media_contracts.ActivityMediaCreate],
    activity_id: int,
    db: Session,
) -> None:
    """Restore media records for one activity.

    Args:
        media: Media records to restore.
        activity_id: ID of the parent activity.
        db: Database session.
    """
    activity_media_crud.create_activity_medias(media, activity_id, db)


def _restore_profile_records(
    records: list[dict[str, Any]],
    original_activity_id: int,
    new_activity: activity_schema.ActivityRead,
    db: Session,
) -> int:
    """Validate and restore profile media records for one activity.

    Args:
        records: Profile records to restore.
        original_activity_id: The activity's ID in the exported archive.
        new_activity: The activity the records are restored onto.
        db: Database session.

    Returns:
        The number of records restored.
    """
    media: list[activity_media_contracts.ActivityMediaCreate] = []
    for record in records:
        if record.get("activity_id") != original_activity_id:
            continue
        data = dict(record)
        old_key = data.get("media_path")
        if not old_key:
            continue
        media_path = activity_media_service.rekey_media_path(str(old_key), new_activity.id)
        if media_path is None:
            logger.warning(
                "Skipping activity media with invalid key",
                extra=core_logger.context(media_path=old_key),
            )
            continue
        media.append(
            activity_media_contracts.ActivityMediaCreate(
                media_path=media_path,
                media_type=data.get("media_type", 1),
            )
        )

    if media:
        _restore_media_records(media, new_activity.id, db)
    return len(media)


def profile_contributor() -> activities_contributors.ProfileActivityContributor:
    """Return the activity-media profile contribution.

    Returns:
        The contributor.
    """
    return activities_contributors.ProfileActivityContributor(
        key="media",
        archive_path="data/activity_media.json",
        count_key="activity_media",
        split=False,
        export=_list_media_for_activities,
        restore=_restore_profile_records,
    )


def attach_media_bytes(
    activity_id: int,
    original_filename: str | None,
    data: bytes,
    db: Session,
) -> activity_media_contracts.ActivityMediaRecord:
    """Attach already-validated image bytes to an activity.

    A server-side import calls this with no request to carry the provider, so
    this surface function is the point that resolves it.

    Args:
        activity_id: ID of the activity.
        original_filename: The client's original filename, or None.
        data: The parsed component payload.
        db: Database session.

    Returns:
        The stored media record.
    """
    storage = platform_runtime.get_active_platform().storage
    return activity_media_service.store_activity_media_bytes(activity_id, original_filename, data, storage, db)


def list_media_blobs(
    activity_id: int,
    storage: platform_providers.StorageProvider,
) -> list[tuple[str, bytes]]:
    """Return every readable media blob attached to an activity.

    Args:
        activity_id: ID of the activity.
        storage: The blob-storage provider.

    Returns:
        Every readable media blob attached to an activity.
    """
    return activity_media_service.list_media_blobs(activity_id, storage)


def store_media_blob(
    activity_id: int,
    suffix: str,
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> str:
    """Restore one exported media blob and return its storage key.

    Args:
        activity_id: ID of the activity.
        suffix: Storage-key suffix of the blob.
        extension: File extension of the blob, including the dot.
        data: The parsed component payload.
        storage: The blob-storage provider.

    Returns:
        The storage key the blob was stored under.
    """
    return activity_media_service.store_media_blob(activity_id, suffix, extension, data, storage)
