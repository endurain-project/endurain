"""Application logic for activity media (photos attached to an activity).

Owns everything that is not persistence: the ownership checks, the
server-generated storage filename, writing the validated upload to the storage
directory, and removing the file when the record goes away. ``crud.py`` is left
as pure persistence, and the router is left as a thin HTTP adapter — previously
both of those carried pieces of this logic, so an ownership rule lived in three
places at once.
"""

import uuid
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
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
    """Raise :class:`NotFoundError` unless ``user_id`` owns ``activity_id``.

    "Not found" rather than "forbidden" so a caller cannot use the media endpoints
    to probe which activity ids exist.

    Args:
        activity_id: The activity the media belongs to.
        user_id: The authenticated user.
        db: Database session.

    Returns:
        None.

    Raises:
        NotFoundError: When the activity does not exist or is not owned by the
            user.
    """
    if activity_crud.get_activity_by_id_from_user_id(activity_id, user_id, db) is None:
        logger.debug(
            "Rejected activity media access for an activity the caller does not own",
            extra=core_logger.context(activity_id=activity_id, user_id=user_id),
        )
        raise core_exceptions.NotFoundError("Activity not found")


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
        UnsupportedMediaTypeError: When the extension is not allowed.
    """
    base_name = PurePosixPath(original_name or "").name
    extension = PurePosixPath(base_name).suffix.lower()

    if extension not in _ALLOWED_MEDIA_EXTENSIONS:
        logger.debug(
            "Rejected an activity media upload with an unsupported extension",
            extra=core_logger.context(activity_id=activity_id, extension=extension or None),
        )
        raise core_exceptions.UnsupportedMediaTypeError("Unsupported media file type")

    return f"{activity_id}_{uuid.uuid4().hex}{extension}"


def list_activity_media(
    activity_id: int,
    user_id: int,
    db: Session,
) -> list[activity_media_schema.ActivityMedia]:
    """List the media attached to one of the user's activities.

    Args:
        activity_id: The activity whose media to list.
        user_id: The authenticated user.
        db: Database session.

    Returns:
        The activity's media, empty when the activity is not the user's or has
        no media. A collection read returns a collection; "you cannot see it"
        and "there is none" are deliberately indistinguishable here so the
        endpoint cannot be used to probe which activity ids exist.
    """
    if activity_crud.get_activity_by_id_from_user_id(activity_id, user_id, db) is None:
        return []
    return activity_media_crud.get_media_for_activity(activity_id, db) or []


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
        NotFoundError: When the activity is not the user's.
        UnsupportedMediaTypeError: For an unsupported extension.
        ConflictError: On a duplicate path.
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
    except (core_exceptions.DomainError, HTTPException):
        # Best-effort cleanup of the orphaned file, confined to the media dir.
        try:
            core_file_uploads.safe_remove_within(
                file_path,
                base_dir=core_config.settings.ACTIVITY_MEDIA_DIR,
            )
        except HTTPException as fs_err:
            logger.warning(
                "Failed to clean up an orphaned activity media file",
                extra=core_logger.context(activity_id=activity_id, file=storage_name, reason=fs_err.detail),
            )
        raise

    logger.info(
        "Stored activity media",
        extra=core_logger.context(activity_id=activity_id, user_id=user_id, media_id=created.id),
    )
    return created


def delete_activity_media(activity_id: int, media_id: int, user_id: int, db: Session) -> None:
    """Delete one of the user's media records and its file on disk.

    Args:
        activity_id: The activity the media must belong to, taken from the route
            path. Checked so a media id cannot be deleted through an unrelated
            activity's URL.
        media_id: The media record to delete.
        user_id: The authenticated user, who must own the owning activity.
        db: Database session.

    Returns:
        None.

    Raises:
        NotFoundError: When the media does not exist, does not belong to
            ``activity_id``, or its activity is not the user's.
    """
    media = activity_media_crud.get_activity_media_by_id(media_id, db)
    if media is None or media.activity_id != activity_id:
        raise core_exceptions.NotFoundError("Activity media not found")

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
                "Refused to remove an activity media file outside the media directory",
                extra=core_logger.context(media_id=media_id, reason=fs_err.detail),
            )

    logger.info(
        "Deleted activity media",
        extra=core_logger.context(media_id=media_id, user_id=user_id),
    )


def delete_media_files_for_activity(activity_id: int) -> int:
    """Remove every stored media file belonging to one activity.

    Used by the ``activity.deleted`` cleanup subscriber. It works from the
    activity id alone and never touches the database, which is the only thing
    that *can* work here: ``activity_media`` rows are ``ON DELETE CASCADE``, so by
    the time the event is handled the rows carrying ``media_path`` are already
    gone. Stored filenames are ``{activity_id}_{uuid}{ext}``, so the id is enough
    to find them.

    Idempotent, and safe to run for an activity that never had media.

    Args:
        activity_id: The deleted activity whose media files to remove.

    Returns:
        The number of files removed.
    """
    media_dir = Path(core_config.settings.ACTIVITY_MEDIA_DIR)
    if not media_dir.is_dir():
        return 0

    base = media_dir.resolve()
    removed = 0
    # ``activity_id`` is an int, so the pattern cannot contain glob or traversal
    # metacharacters. The trailing underscore keeps activity 42 from matching
    # activity 421's files.
    for candidate in media_dir.glob(f"{activity_id}_*"):
        resolved = candidate.resolve()
        # Defence in depth: never follow a symlink out of the media directory.
        if not resolved.is_relative_to(base) or not resolved.is_file():
            continue
        try:
            resolved.unlink()
            removed += 1
        except OSError as err:
            logger.warning(
                "Failed to remove an activity media file",
                extra=core_logger.context(activity_id=activity_id, file=candidate.name, reason=str(err)),
            )

    if removed:
        logger.info(
            "Removed media files for a deleted activity",
            extra=core_logger.context(activity_id=activity_id, removed=removed),
        )
    return removed
