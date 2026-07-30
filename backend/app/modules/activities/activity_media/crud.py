"""Persistence for activity media records.

Pure persistence: ownership checks, upload handling and blob cleanup live in
``service.py``, so this module never reaches into another subpackage's CRUD and
never touches storage. It returns the internal
:class:`~modules.activities.activity_media.contracts.ActivityMediaRecord`, which
carries the storage key; turning that key into a servable URL is an addressing
concern owned by ``service.py``, not by the persistence layer.
"""

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.models as activity_models
import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.models as activity_media_models

logger = core_logger.get_logger(__name__)


def _to_record(
    orm_media: activity_media_models.ActivityMedia,
) -> activity_media_contracts.ActivityMediaRecord:
    """Convert an ORM ``ActivityMedia`` row to its record.

    The single ORM→record boundary for this module, so ORM instances never leave
    ``crud``.
    """
    return activity_media_contracts.ActivityMediaRecord.model_validate(orm_media)


@core_decorators.handle_db_errors
def get_all_activity_media(
    db: Session,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """
    Retrieve every activity media record in the database.

    Args:
        db: Database session.

    Returns:
        The media records (empty if none exist).

    Raises:
        ProcessingError: If a database error occurs.
    """
    stmt = select(activity_media_models.ActivityMedia)
    return [_to_record(media) for media in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def get_activity_media_by_id(
    activity_media_id: int,
    db: Session,
) -> activity_media_contracts.ActivityMediaRecord | None:
    """
       Retrieve a single media record by id, without any permission check.

       Args:
           activity_media_id: The media record to fetch.
           db: Database session.

       Returns:
    The media record, or None when no such record exists.

       Raises:
           ProcessingError: If a database error occurs.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.id == activity_media_id
    )
    media = db.scalars(stmt).first()
    return _to_record(media) if media is not None else None


@core_decorators.handle_db_errors
def get_media_for_activity(
    activity_id: int,
    db: Session,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """
    Retrieve all media records for a single activity.

    Permission is the caller's concern; see
    :func:`modules.activities.activity_media.service.list_activity_media`.

    Args:
        activity_id: Activity ID to fetch media for.
        db: Database session.

    Returns:
        The activity's media records (empty when it has none).

    Raises:
        ProcessingError: If a database error occurs.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.activity_id == activity_id
    )
    return [_to_record(media) for media in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def get_activities_media(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """
    Retrieve media records for the activities owned by the user.

    Args:
        activity_ids: Activity IDs to consider.
        token_user_id: ID of the user making the request.
        db: Database session.

    Returns:
        The media records for activities owned by the user
        (empty if none match).

    Raises:
        ProcessingError: If a database error occurs.
    """
    if not activity_ids:
        return []

    allowed_stmt = select(activity_models.Activity.id).where(
        activity_models.Activity.id.in_(activity_ids),
        activity_models.Activity.user_id == token_user_id,
    )
    allowed_ids = list(db.scalars(allowed_stmt).all())
    if not allowed_ids:
        return []

    media_stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.activity_id.in_(allowed_ids)
    )
    return [_to_record(media) for media in db.scalars(media_stmt).all()]


@core_decorators.handle_db_errors
def get_media_with_legacy_path(
    db: Session,
    after_id: int = 0,
    limit: int = 200,
) -> list[activity_media_contracts.ActivityMediaRecord]:
    """Return media rows whose stored value is a legacy filesystem path.

    Legacy values are absolute paths (they contain a ``/`` or ``\\`` separator);
    the storage keys that replaced them (e.g. ``42_ab12.jpg``) never do. Ordered
    by id and paged via ``after_id`` so the data migration can process them in
    bounded batches (migration use only).

    Args:
        db: Database session.
        after_id: Return only media with ``id`` greater than this.
        limit: Maximum number of rows to return.

    Returns:
        The matching media records.
    """
    stmt = (
        select(activity_media_models.ActivityMedia)
        .where(
            activity_media_models.ActivityMedia.media_path.isnot(None),
            or_(
                activity_media_models.ActivityMedia.media_path.like("%/%"),
                activity_media_models.ActivityMedia.media_path.like("%\\%"),
            ),
            activity_media_models.ActivityMedia.id > after_id,
        )
        .order_by(activity_media_models.ActivityMedia.id)
        .limit(limit)
    )
    return [_to_record(media) for media in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def create_activity_media(
    activity_id: int, media_key: str, db: Session
) -> activity_media_contracts.ActivityMediaRecord:
    """
    Create a new activity media record.

    Args:
        activity_id: Activity ID the media belongs to.
        media_key: ``StorageProvider`` key the blob was saved under.
        db: Database session.

    Returns:
        The newly created media record.

    Raises:
        ConflictError: If a record with the same ``media_path`` exists.
        ProcessingError: For any other database error.
    """
    try:
        db_activity_media = activity_media_models.ActivityMedia(
            activity_id=activity_id,
            media_path=media_key,
            media_type=1,
        )
        db.add(db_activity_media)
        db.commit()
        db.refresh(db_activity_media)
        logger.debug(
            "Created activity media",
            extra=core_logger.context(activity_id=activity_id, media_id=db_activity_media.id),
        )
        return _to_record(db_activity_media)
    except IntegrityError as integrity_error:
        db.rollback()
        raise core_exceptions.ConflictError(
            "Duplicate entry error. Check if path and file name are unique."
        ) from integrity_error


@core_decorators.handle_db_errors
def create_activity_medias(
    activity_media: list[activity_media_contracts.ActivityMediaCreate],
    activity_id: int,
    db: Session,
) -> None:
    """
    Persist a batch of activity media records for a single activity.

    Args:
        activity_media: The media records to persist.
        activity_id: Activity ID the media belong to.
        db: Database session.

    Returns:
        None.

    Raises:
        ProcessingError: If a database error occurs.
    """
    media: list[activity_media_models.ActivityMedia] = []
    for media_item in activity_media:
        media.append(
            activity_media_models.ActivityMedia(
                activity_id=activity_id,
                media_path=media_item.media_path,
                media_type=media_item.media_type,
            )
        )

    if not media:
        return

    db.add_all(media)
    db.commit()


@core_decorators.handle_db_errors
def edit_activity_media_media_path(
    activity_media_id: int, media_path: str, db: Session
) -> activity_media_contracts.ActivityMediaRecord:
    """
    Update the ``media_path`` of an activity media record.

    Args:
        activity_media_id: ID of the activity media record to update.
        media_path: New filesystem path to assign.
        db: Database session.

    Returns:
        The refreshed media record.

    Raises:
        NotFoundError: If the record does not exist.
        ProcessingError: For any other database error.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.id == activity_media_id
    )
    db_activity_media = db.scalars(stmt).first()

    if db_activity_media is None:
        raise core_exceptions.NotFoundError("Activity media not found")

    db_activity_media.media_path = media_path
    db.commit()
    db.refresh(db_activity_media)
    logger.debug("Updated the activity media path", extra=core_logger.context(media_id=activity_media_id))
    return _to_record(db_activity_media)


@core_decorators.handle_db_errors
def delete_activity_media(activity_media_id: int, db: Session) -> None:
    """
    Delete an activity media record.

    Permission and file cleanup are the caller's concern; see
    :func:`modules.activities.activity_media.service.delete_activity_media`.

    Args:
        activity_media_id: ID of the activity media record to delete.
        db: Database session.

    Returns:
        None.

    Raises:
        NotFoundError: If the media record does not exist.
        ProcessingError: For database errors.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.id == activity_media_id
    )
    activity_media = db.scalars(stmt).first()

    if not activity_media:
        raise core_exceptions.NotFoundError("Activity media not found")

    db.delete(activity_media)
    db.commit()
    logger.debug("Deleted activity media", extra=core_logger.context(media_id=activity_media_id))
