"""Persistence for activity media records.

Pure persistence: ownership checks, upload handling and file cleanup live in
``service.py``, so this module never reaches into another subpackage's CRUD and
never touches the filesystem.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity.models as activity_models
import modules.activities.activity_media.models as activity_media_models
import modules.activities.activity_media.schema as activity_media_schema

logger = core_logger.get_logger(__name__)


def _to_read_schema(
    orm_media: activity_media_models.ActivityMedia,
) -> activity_media_schema.ActivityMedia:
    """Convert an ORM ``ActivityMedia`` row to its read schema.

    The single ORM→schema boundary for this module so ORM instances never leave
    ``crud``.
    """
    return activity_media_schema.ActivityMedia.model_validate(orm_media)


@core_decorators.handle_db_errors
def get_all_activity_media(
    db: Session,
) -> list[activity_media_schema.ActivityMedia]:
    """
    Retrieve every activity media record in the database.

    Args:
        db: Database session.

    Returns:
        List of ActivityMedia schemas (empty if none exist).

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(activity_media_models.ActivityMedia)
    return [_to_read_schema(media) for media in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def get_activity_media_by_id(
    activity_media_id: int,
    db: Session,
) -> activity_media_schema.ActivityMedia | None:
    """
       Retrieve a single media record by id, without any permission check.

       Args:
           activity_media_id: The media record to fetch.
           db: Database session.

       Returns:
    The ActivityMedia schema, or None when no such record exists.

       Raises:
           HTTPException: If a database error occurs.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.id == activity_media_id
    )
    media = db.scalars(stmt).first()
    return _to_read_schema(media) if media is not None else None


@core_decorators.handle_db_errors
def get_media_for_activity(
    activity_id: int,
    db: Session,
) -> list[activity_media_schema.ActivityMedia]:
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
        HTTPException: If a database error occurs.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.activity_id == activity_id
    )
    return [_to_read_schema(media) for media in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def get_activities_media(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
) -> list[activity_media_schema.ActivityMedia]:
    """
    Retrieve media records for the activities owned by the user.

    Args:
        activity_ids: Activity IDs to consider.
        token_user_id: ID of the user making the request.
        db: Database session.

    Returns:
        List of ActivityMedia schemas for activities owned by the user
        (empty if none match).

    Raises:
        HTTPException: If a database error occurs.
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
    return [_to_read_schema(media) for media in db.scalars(media_stmt).all()]


@core_decorators.handle_db_errors
def create_activity_media(activity_id: int, media_path: str, db: Session) -> activity_media_schema.ActivityMedia:
    """
    Create a new activity media record.

    Args:
        activity_id: Activity ID the media belongs to.
        media_path: Filesystem path to the stored media file.
        db: Database session.

    Returns:
        The newly created ActivityMedia schema.

    Raises:
        HTTPException:
            - 409 Conflict: If a record with the same ``media_path`` exists.
            - 500 Internal Server Error: For any other database error.
    """
    try:
        db_activity_media = activity_media_models.ActivityMedia(
            activity_id=activity_id,
            media_path=media_path,
            media_type=1,
        )
        db.add(db_activity_media)
        db.commit()
        db.refresh(db_activity_media)
        logger.debug(f"Created activity media {db_activity_media.id} for activity {activity_id}")
        return _to_read_schema(db_activity_media)
    except IntegrityError as integrity_error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Duplicate entry error. Check if path and file name are unique."),
        ) from integrity_error


@core_decorators.handle_db_errors
def create_activity_medias(
    activity_media: list[activity_media_schema.ActivityMedia],
    activity_id: int,
    db: Session,
) -> None:
    """
    Persist a batch of activity media records for a single activity.

    Args:
        activity_media: List of ActivityMedia Pydantic schemas.
        activity_id: Activity ID the media belong to.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If a database error occurs.
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
) -> activity_media_schema.ActivityMedia:
    """
    Update the ``media_path`` of an activity media record.

    Args:
        activity_media_id: ID of the activity media record to update.
        media_path: New filesystem path to assign.
        db: Database session.

    Returns:
        The refreshed ActivityMedia schema.

    Raises:
        HTTPException:
            - 404 Not Found: If the record does not exist.
            - 500 Internal Server Error: For any other database error.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.id == activity_media_id
    )
    db_activity_media = db.scalars(stmt).first()

    if db_activity_media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity media not found",
        )

    db_activity_media.media_path = media_path
    db.commit()
    db.refresh(db_activity_media)
    logger.debug(f"Updated media path for activity media {activity_media_id}")
    return _to_read_schema(db_activity_media)


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
        HTTPException:
            - 404 Not Found: If the media record does not exist.
            - 500 Internal Server Error: For database errors.
    """
    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.id == activity_media_id
    )
    activity_media = db.scalars(stmt).first()

    if not activity_media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity media not found",
        )

    db.delete(activity_media)
    db.commit()
    logger.debug(f"Deleted activity media {activity_media_id}")
