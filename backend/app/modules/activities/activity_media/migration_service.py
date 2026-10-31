"""The activity-media operations exposed only to data migrations."""

from sqlalchemy.orm import Session

import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.signing as activity_media_signing

MEDIA_STORAGE_AREA = activity_media_signing.MEDIA_STORAGE_AREA
get_all_activity_media = activity_media_crud.get_all_activity_media
get_media_with_legacy_path = activity_media_crud.get_media_with_legacy_path


def edit_activity_media_media_path(
    activity_media_id: int, media_path: str, db: Session
) -> activity_media_contracts.ActivityMediaRecord:
    """Update a media record's path and commit it, as migrations did.

    Args:
        activity_media_id: ID of the media record.
        media_path: The new path or storage key.
        db: Database session.

    Returns:
        The refreshed media record.
    """
    record = activity_media_crud.edit_activity_media_media_path(activity_media_id, media_path, db)
    db.commit()
    return record


def delete_activity_media(activity_media_id: int, db: Session) -> None:
    """Delete a media record and commit it, as migrations did.

    Args:
        activity_media_id: ID of the media record to delete.
        db: Database session.
    """
    activity_media_crud.delete_activity_media(activity_media_id, db)
    db.commit()
