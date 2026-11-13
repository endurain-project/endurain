"""Persistence for activity media records.

Pure persistence: ownership checks, upload handling and blob cleanup live in
``service.py``, so this module never reaches into another subpackage's CRUD and
never touches storage. It returns the internal
:class:`~modules.activities.activity_media.contracts.ActivityMediaRecord`, which
carries the storage key; turning that key into a servable URL is an addressing
concern owned by ``service.py``, not by the persistence layer.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.models as activity_media_models
import modules.activities.activity_media.serializers as activity_media_serializers

#: The gap between the creation times of the photos of one batch, so they sort in the order they were given.
_PHOTO_SPACING = timedelta(microseconds=1)


def get_all_activity_media(
    db: Session,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """Retrieve every activity media record in the database.

    Args:
        db: Database session.

    Returns:
        The media records (empty if none exist).
    """
    stmt = select(activity_media_models.ActivityMedia)
    return [activity_media_serializers.to_read_schema(media) for media in db.scalars(stmt).all()]


def replace_activity_media_paths(changes: Sequence[tuple[uuid.UUID, str, str]], db: Session) -> None:
    """Stage new storage keys, each only where the media record still holds the key it was read with.

    The caller commits.

    Args:
        changes: ``(media id, current media_path, new media_path)`` triples.
        db: Database session.
    """
    for media_id, old_path, new_path in changes:
        db.execute(
            update(activity_media_models.ActivityMedia)
            .where(
                activity_media_models.ActivityMedia.id == media_id,
                activity_media_models.ActivityMedia.media_path == old_path,
            )
            .values(media_path=new_path)
        )
    db.flush()


def get_activity_media_by_id(
    activity_media_id: uuid.UUID,
    db: Session,
) -> activity_media_contracts.ActivityMediaRecord | None:
    """Retrieve a single media record by id, without any permission check.

    Args:
        activity_media_id: The media record to fetch.
        db: Database session.

    Returns:
        The media record, or None when no such record exists.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.id == activity_media_id
    )
    media = db.scalars(stmt).first()
    return activity_media_serializers.to_read_schema(media) if media is not None else None


def get_media_for_activity(
    activity_id: uuid.UUID,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = 200,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """Retrieve one page of a single activity's media records, oldest first.

    Permission is the caller's concern; see
    :func:`modules.activities.activity_media.service.list_activity_media`.

    Args:
        activity_id: Activity ID to fetch media for.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page of media records (empty when the activity has none).
    """
    stmt = (
        select(activity_media_models.ActivityMedia)
        .where(activity_media_models.ActivityMedia.activity_id == activity_id)
        .order_by(activity_media_models.ActivityMedia.created_at, activity_media_models.ActivityMedia.id)
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    return [activity_media_serializers.to_read_schema(media) for media in db.scalars(stmt).all()]


def count_media_for_activity(activity_id: uuid.UUID, db: Session) -> int:
    """Count an activity's media records.

    Args:
        activity_id: Activity ID to count media for.
        db: Database session.

    Returns:
        The total number of media records.
    """
    stmt = select(func.count()).where(activity_media_models.ActivityMedia.activity_id == activity_id)
    return db.scalar(stmt) or 0


def get_activities_media(
    activity_ids: list[uuid.UUID],
    db: Session,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """Retrieve the media records of several activities at once.

    Performs no access check and joins no parent row: which activities the
    caller may read is decided before this is reached, by the activities
    integration service that owns them.

    Args:
        activity_ids: The activities to read, already scoped to the caller.
        db: Database session.

    Returns:
        The media records of those activities, empty when there are none.
    """
    if not activity_ids:
        return []

    stmt = (
        select(activity_media_models.ActivityMedia)
        .where(activity_media_models.ActivityMedia.activity_id.in_(activity_ids))
        .order_by(activity_media_models.ActivityMedia.created_at, activity_media_models.ActivityMedia.id)
    )
    return [activity_media_serializers.to_read_schema(media) for media in db.scalars(stmt).all()]


def get_media_for_owned_activities(
    activity_ids: list[uuid.UUID],
    db: Session,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """Retrieve the media records of several activities the requester owns, oldest first, in one query.

    Performs no access check: the activities service passes only IDs of activities the
    requester owns, which is the rule :func:`get_media_for_activity` leaves to its caller.

    Args:
        activity_ids: The activities to read, already scoped to their owner.
        db: Database session.

    Returns:
        The media records of those activities, empty when there are none.
    """
    if not activity_ids:
        return []

    stmt = (
        select(activity_media_models.ActivityMedia)
        .where(activity_media_models.ActivityMedia.activity_id.in_(activity_ids))
        .order_by(activity_media_models.ActivityMedia.created_at, activity_media_models.ActivityMedia.id)
    )
    return [activity_media_serializers.to_read_schema(media) for media in db.scalars(stmt).all()]


def get_existing_media_paths(media_paths: list[str], db: Session) -> set[str]:
    """Return which of the given storage keys a media record still names.

    Args:
        media_paths: Storage keys to look up.
        db: Database session.

    Returns:
        The subset of ``media_paths`` held by a record.
    """
    if not media_paths:
        return set()
    stmt = select(activity_media_models.ActivityMedia.media_path).where(
        activity_media_models.ActivityMedia.media_path.in_(media_paths)
    )
    return {path for path in db.scalars(stmt).all() if path is not None}


def get_activity_media_by_content_hash(
    activity_id: uuid.UUID,
    content_hash: str,
    db: Session,
) -> activity_media_contracts.ActivityMediaRecord | None:
    """Get an activity's media record by the content hash of its bytes.

    Used to make re-storing the same photo for an activity a no-op — a retried
    upload, or a Strava bulk-export re-run — the media counterpart of
    :func:`modules.activities.activity.crud.get_activity_by_dedup_key`.

    Args:
        activity_id: The activity the media must belong to.
        content_hash: SHA-256 of the media bytes.
        db: Database session.

    Returns:
        The matching media record, or None when there isn't one.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.activity_id == activity_id,
        activity_media_models.ActivityMedia.content_hash == content_hash,
    )
    media = db.scalars(stmt).first()
    return activity_media_serializers.to_read_schema(media) if media is not None else None


def create_activity_media(
    activity_id: uuid.UUID,
    media_key: str,
    db: Session,
    *,
    content_hash: str | None = None,
) -> activity_media_contracts.ActivityMediaRecord:
    """Stage a new activity media record (flushed, not committed).

    Args:
        activity_id: Activity ID the media belongs to.
        media_key: ``StorageProvider`` key the blob was saved under.
        db: Database session.
        content_hash: SHA-256 of the media bytes, when known. Persisted so a
            later store of the same photo for this activity can be recognised
            as a duplicate instead of creating a second row.

    Returns:
        The newly created media record.

    Raises:
        ConflictError: If a record with the same ``media_path`` exists, or the
            same ``content_hash`` is already stored for this activity.
    """
    try:
        db_activity_media = activity_media_models.ActivityMedia(
            activity_id=activity_id,
            media_path=media_key,
            media_type=activity_constants.MediaType.PHOTO.stored,
            content_hash=content_hash,
            created_at=datetime.now(UTC),
        )
        db.add(db_activity_media)
        db.flush()
        db.refresh(db_activity_media)
        return activity_media_serializers.to_read_schema(db_activity_media)
    except IntegrityError as integrity_error:
        raise core_exceptions.ConflictError(
            "Duplicate entry error. Check if path/file name or content are unique."
        ) from integrity_error


def create_activity_medias(
    activity_media: list[activity_media_contracts.ActivityMediaCreate],
    activity_id: uuid.UUID,
    db: Session,
) -> None:
    """Stage a batch of activity media records for a single activity.

    Args:
        activity_media: The media records to persist.
        activity_id: Activity ID the media belong to.
        db: Database session.
    """
    media: list[activity_media_models.ActivityMedia] = []
    created_at = datetime.now(UTC)
    for position, media_item in enumerate(activity_media):
        media.append(
            activity_media_models.ActivityMedia(
                activity_id=activity_id,
                media_path=media_item.media_path,
                media_type=media_item.media_type.stored,
                content_hash=media_item.content_hash,
                created_at=created_at + position * _PHOTO_SPACING,
            )
        )

    if not media:
        return

    db.add_all(media)
    db.flush()


def delete_activity_media(activity_media_id: uuid.UUID, db: Session) -> None:
    """Stage the deletion of an activity media record.

    Permission and file cleanup are the caller's concern; see
    :func:`modules.activities.activity_media.service.delete_activity_media`.

    Args:
        activity_media_id: ID of the activity media record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the media record does not exist.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.id == activity_media_id
    )
    activity_media = db.scalars(stmt).first()

    if not activity_media:
        raise core_exceptions.NotFoundError("Activity media not found")

    db.delete(activity_media)
    db.flush()
