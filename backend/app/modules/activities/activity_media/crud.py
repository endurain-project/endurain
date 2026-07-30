"""CRUD operations for activity media records."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.config as core_config
import core.decorators as core_decorators
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
import modules.activities.activity_media.models as activity_media_models
import modules.activities.activity_media.schema as activity_media_schema


@core_decorators.handle_db_errors
def get_all_activity_media(
    db: Session,
) -> list[activity_media_models.ActivityMedia]:
    """
    Retrieve every activity media record in the database.

    Args:
        db: Database session.

    Returns:
        List of ActivityMedia models (empty if none exist).

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(activity_media_models.ActivityMedia)
    return list(db.scalars(stmt).all())


@core_decorators.handle_db_errors
def get_activity_media(
    activity_id: int, token_user_id: int, db: Session
) -> list[activity_media_models.ActivityMedia] | None:
    """
    Retrieve all media records for a single activity owned by the user.

    Args:
        activity_id: Activity ID to fetch media for.
        token_user_id: ID of the user making the request.
        db: Database session.

    Returns:
        List of ActivityMedia models, or None if the activity is not
        accessible or has no media.

    Raises:
        HTTPException: If a database error occurs.
    """
    activity = activity_crud.get_activity_by_id_from_user_id(activity_id, token_user_id, db)
    if not activity:
        return None

    stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.activity_id == activity_id
    )
    activity_media = list(db.scalars(stmt).all())

    if not activity_media:
        return None

    return activity_media


@core_decorators.handle_db_errors
def get_activities_media(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    activities: list[activity_models.Activity] | None = None,
) -> list[activity_media_models.ActivityMedia]:
    """
    Retrieve media records for the activities owned by the user.

    Args:
        activity_ids: Activity IDs to consider.
        token_user_id: ID of the user making the request.
        db: Database session.
        activities: Optional pre-fetched activity ORM instances; if not
            provided they will be fetched from the database.

    Returns:
        List of ActivityMedia models for activities owned by the user
        (empty if none match).

    Raises:
        HTTPException: If a database error occurs.
    """
    if not activity_ids:
        return []

    if not activities:
        activity_stmt = select(activity_models.Activity).where(activity_models.Activity.id.in_(activity_ids))
        activities = list(db.scalars(activity_stmt).all())

    if not activities:
        return []

    allowed_ids = [activity.id for activity in activities if activity.user_id == token_user_id]
    if not allowed_ids:
        return []

    media_stmt = select(activity_media_models.ActivityMedia).where(
        activity_media_models.ActivityMedia.activity_id.in_(allowed_ids)
    )
    return list(db.scalars(media_stmt).all())


@core_decorators.handle_db_errors
def create_activity_media(activity_id: int, media_path: str, db: Session) -> activity_media_models.ActivityMedia:
    """
    Create a new activity media record.

    Args:
        activity_id: Activity ID the media belongs to.
        media_path: Filesystem path to the stored media file.
        db: Database session.

    Returns:
        The newly created ActivityMedia model instance.

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
        return db_activity_media
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
) -> activity_media_models.ActivityMedia:
    """
    Update the ``media_path`` of an activity media record.

    Args:
        activity_media_id: ID of the activity media record to update.
        media_path: New filesystem path to assign.
        db: Database session.

    Returns:
        The refreshed ActivityMedia model instance.

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
    return db_activity_media


@core_decorators.handle_db_errors
def delete_activity_media(activity_media_id: int, token_user_id: int, db: Session) -> None:
    """
    Delete an activity media record and its underlying file.

    The file deletion is restricted to paths inside the configured
    ``ACTIVITY_MEDIA_DIR`` to prevent arbitrary file deletion (defense in
    depth against tampered ``media_path`` values).

    Args:
        activity_media_id: ID of the activity media record to delete.
        token_user_id: ID of the user making the request.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException:
            - 404 Not Found: If the media or owning activity does not exist.
            - 403 Forbidden: If the user does not own the activity.
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

    activity = activity_crud.get_activity_by_id_from_user_id(activity_media.activity_id, token_user_id, db)
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    if activity.user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this media",
        )

    media_path = activity_media.media_path

    db.delete(activity_media)
    db.commit()

    # Best-effort filesystem cleanup, confined to ACTIVITY_MEDIA_DIR.
    if media_path:
        try:
            core_file_uploads.safe_remove_within(
                media_path,
                base_dir=core_config.settings.ACTIVITY_MEDIA_DIR,
            )
        except HTTPException as fs_err:
            core_logger.print_to_log(
                f"Refused to remove activity media outside media dir for id {activity_media_id}: {fs_err.detail}",
                "warning",
            )
