"""Application logic for activity media (photos attached to an activity).

Owns everything that is not persistence: the ownership checks, the
server-generated storage filename, writing the validated upload to the storage
directory, and removing the file when the record goes away. ``crud.py`` is left
as pure persistence, and the router is left as a thin HTTP adapter — previously
both of those carried pieces of this logic, so an ownership rule lived in three
places at once.
"""

import uuid
from pathlib import PurePosixPath

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import core.config as core_config
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity.crud as activity_crud
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.schema as activity_media_schema

logger = core_logger.get_logger(__name__)

# Allow-list of safe image extensions for activity media uploads. The upload is
# also magic-number validated by safeuploads; this only bounds the extension we
# are willing to write to disk.
_ALLOWED_MEDIA_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"})


def _require_owned_activity(activity_id: int, user_id: int, db: Session) -> None:
    """Raise 404 unless ``user_id`` owns ``activity_id``.

    404 rather than 403 so a caller cannot use the media endpoints to probe which
    activity ids exist.

    Args:
        activity_id: The activity the media belongs to.
        user_id: The authenticated user.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: 404 when the activity does not exist or is not owned by
            the user.
    """
    if activity_crud.get_activity_by_id_from_user_id(activity_id, user_id, db) is None:
        logger.debug(
            "Rejected activity media access for an activity the caller does not own",
            extra=core_logger.context(activity_id=activity_id, user_id=user_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )


def _build_storage_filename(activity_id: int, original_name: str | None) -> str:
    """Build a path-traversal-safe storage filename for an uploaded media file.

    The original filename is reduced to its basename and its extension checked
    against the allow-list; the stored name is then generated server-side, so a
    hostile filename can neither escape the media directory nor be echoed back.

    Args:
        activity_id: ID of the activity the media belongs to.
        original_name: Original ``UploadFile.filename`` value.

    Returns:
        A safe filename of the form ``"{activity_id}_{uuid}{ext}"``.

    Raises:
        HTTPException: 415 when the extension is not allowed.
    """
    base_name = PurePosixPath(original_name or "").name
    extension = PurePosixPath(base_name).suffix.lower()

    if extension not in _ALLOWED_MEDIA_EXTENSIONS:
        logger.debug(
            "Rejected an activity media upload with an unsupported extension",
            extra=core_logger.context(activity_id=activity_id, extension=extension or None),
        )
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported media file type",
        )

    return f"{activity_id}_{uuid.uuid4().hex}{extension}"


def list_activity_media(
    activity_id: int,
    user_id: int,
    db: Session,
) -> list[activity_media_schema.ActivityMedia] | None:
    """List the media attached to one of the user's activities.

    Args:
        activity_id: The activity whose media to list.
        user_id: The authenticated user.
        db: Database session.

    Returns:
        The activity's media, or ``None`` when the activity is not the user's or
        has no media.
    """
    if activity_crud.get_activity_by_id_from_user_id(activity_id, user_id, db) is None:
        return None
    return activity_media_crud.get_media_for_activity(activity_id, db) or None


def store_activity_media(
    activity_id: int,
    user_id: int,
    file: UploadFile,
    db: Session,
) -> activity_media_schema.ActivityMedia:
    """Persist an uploaded image and register it against an activity.

    The upload is magic-number and size validated before any bytes reach disk,
    then written under a server-generated filename. If the database row cannot be
    created the file is removed again, so a failed upload leaves nothing behind.

    Args:
        activity_id: The activity to attach the media to.
        user_id: The authenticated user, who must own the activity.
        file: The uploaded image.
        db: Database session.

    Returns:
        The created media record.

    Raises:
        HTTPException: 404 when the activity is not the user's, 415 for an
            unsupported extension, 400 when image validation fails, 409 on a
            duplicate path.
    """
    _require_owned_activity(activity_id, user_id, db)

    storage_name = _build_storage_filename(activity_id, file.filename)

    # SafeUploads validates magic number and size before writing to disk. Callers
    # run on a worker thread (the route is synchronous), so the blocking save
    # never touches the event loop.
    file_path = core_file_uploads.save_validated_upload_sync(
        file,
        kind=core_file_uploads.UploadKind.IMAGE,
        upload_dir=core_config.settings.ACTIVITY_MEDIA_DIR,
        filename=storage_name,
    )

    try:
        created = activity_media_crud.create_activity_media(activity_id, file_path, db)
    except HTTPException:
        # Best-effort cleanup of the orphaned file, confined to the media dir.
        try:
            core_file_uploads.safe_remove_within(
                file_path,
                base_dir=core_config.settings.ACTIVITY_MEDIA_DIR,
            )
        except HTTPException as fs_err:
            logger.warning(
                f"Failed to clean up orphaned media file {storage_name}: {fs_err.detail}",
                extra=core_logger.context(activity_id=activity_id),
            )
        raise

    logger.info(
        "Stored activity media",
        extra=core_logger.context(activity_id=activity_id, user_id=user_id, media_id=created.id),
    )
    return created


def delete_activity_media(media_id: int, user_id: int, db: Session) -> None:
    """Delete one of the user's media records and its file on disk.

    Args:
        media_id: The media record to delete.
        user_id: The authenticated user, who must own the owning activity.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: 404 when the media does not exist or its activity is not
            the user's.
    """
    media = activity_media_crud.get_activity_media_by_id(media_id, db)
    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity media not found",
        )

    _require_owned_activity(media.activity_id, user_id, db)

    activity_media_crud.delete_activity_media(media_id, db)

    # Best-effort filesystem cleanup, confined to ACTIVITY_MEDIA_DIR so a
    # tampered media_path cannot delete anything outside it.
    if media.media_path:
        try:
            core_file_uploads.safe_remove_within(
                media.media_path,
                base_dir=core_config.settings.ACTIVITY_MEDIA_DIR,
            )
        except HTTPException as fs_err:
            logger.warning(
                f"Refused to remove activity media outside the media dir for id {media_id}: {fs_err.detail}",
                extra=core_logger.context(media_id=media_id),
            )

    logger.info(
        "Deleted activity media",
        extra=core_logger.context(media_id=media_id, user_id=user_id),
    )
