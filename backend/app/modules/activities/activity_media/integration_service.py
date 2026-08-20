"""Public record and blob operations for activity media."""

import re
from typing import Any

from sqlalchemy.orm import Session

import core.logger as core_logger
import infra.providers as platform_providers
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.service as activity_media_service
import modules.activities.activity_media.signing as activity_media_signing
import modules.activities.contributors as activity_contributors

logger = core_logger.get_logger(__name__)

_MEDIA_KEY_PATTERN = re.compile(r"(?P<activity_id>\d+)_(?P<suffix>[^/\\]+)")


def list_media_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """Return media records for activity IDs already scoped by the caller."""
    return activity_media_crud.get_activities_media(activity_ids, db)


def restore_media_records(
    media: list[activity_media_contracts.ActivityMediaCreate],
    activity_id: int,
    db: Session,
) -> None:
    """Restore media records for one activity."""
    activity_media_crud.create_activity_medias(media, activity_id, db)


def restore_profile_records(
    records: list[dict[str, Any]],
    original_activity_id: int,
    new_activity: activity_schema.Activity,
    db: Session,
) -> int:
    """Validate and restore profile media records for one activity."""
    if new_activity.id is None:
        return 0

    media: list[activity_media_contracts.ActivityMediaCreate] = []
    for record in records:
        if record.get("activity_id") != original_activity_id:
            continue
        data = dict(record)
        old_key = data.get("media_path")
        if not old_key:
            continue
        match = _MEDIA_KEY_PATTERN.fullmatch(str(old_key))
        if match is None:
            logger.warning(
                "Skipping activity media with invalid key",
                extra=core_logger.context(media_path=old_key),
            )
            continue
        media.append(
            activity_media_contracts.ActivityMediaCreate(
                media_path=f"{new_activity.id}_{match.group('suffix')}",
                media_type=data.get("media_type", 1),
            )
        )

    if media:
        restore_media_records(media, new_activity.id, db)
    return len(media)


def profile_contributor() -> activity_contributors.ProfileActivityContributor:
    """Return the activity-media profile contribution."""
    return activity_contributors.ProfileActivityContributor(
        key="media",
        archive_path="data/activity_media.json",
        count_key="activity_media",
        split=False,
        export=list_media_for_activities,
        restore=restore_profile_records,
    )


def attach_media_bytes(
    activity_id: int,
    original_filename: str | None,
    data: bytes,
    db: Session,
) -> activity_media_contracts.ActivityMediaRecord:
    """Attach already-validated image bytes to an activity."""
    return activity_media_service.store_activity_media_bytes(activity_id, original_filename, data, db)


def list_media_blobs(
    activity_id: int,
    storage: platform_providers.StorageProvider,
) -> list[tuple[str, bytes]]:
    """Return every readable media blob attached to an activity."""
    try:
        keys = storage.list_keys(activity_media_signing.MEDIA_STORAGE_AREA, f"{activity_id}_")
    except Exception as err:
        logger.warning(
            "Could not list an activity's media blobs",
            exc_info=err,
            extra=core_logger.context(activity_id=activity_id),
        )
        return []

    blobs: list[tuple[str, bytes]] = []
    for key in keys:
        try:
            data = storage.get(activity_media_signing.MEDIA_STORAGE_AREA, key)
        except Exception as err:
            logger.warning(
                "Could not read a media blob; skipping it",
                exc_info=err,
                extra=core_logger.context(storage_key=key),
            )
            continue
        if data is None:
            logger.warning("Media blob is missing behind its key", extra=core_logger.context(storage_key=key))
            continue
        blobs.append((key, data))
    return blobs


def store_media_blob(
    activity_id: int,
    suffix: str,
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> str:
    """Restore one exported media blob and return its storage key."""
    key = f"{activity_id}_{suffix}{extension}"
    storage.save(activity_media_signing.MEDIA_STORAGE_AREA, key, data)
    return key
