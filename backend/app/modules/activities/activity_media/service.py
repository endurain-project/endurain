"""Application logic for activity media (photos attached to an activity).

Owns everything that is not persistence: the ownership checks, the
server-generated storage key, writing the validated upload through the platform
``StorageProvider``, and removing the blob when the record goes away. ``crud.py``
is left as pure persistence, and the router is left as a thin HTTP adapter —
previously both of those carried pieces of this logic, so an ownership rule lived
in three places at once.

Blobs go through the ``StorageProvider`` rather than to a local directory, the
same as thumbnails and retained source files: photos then survive on object
storage and are reachable only through the token-gated route, instead of being
pinned to one node's disk and served from a public static path.
"""

import uuid
from pathlib import PurePosixPath

from fastapi import UploadFile
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.hashing as core_hashing
import core.logger as core_logger
import infra.providers as platform_providers
import infra.runtime as platform_runtime
import modules.activities.activity.integration_service as activities_service
import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.schema as activity_media_schema
import modules.activities.activity_media.signing as activity_media_signing

logger = core_logger.get_logger(__name__)

# Allow-list of safe image extensions for activity media uploads. The upload is
# also magic-number validated by safeuploads; this only bounds the extension we
# are willing to record in a storage key.
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
    if not activities_service.owns_activity(activity_id, user_id, db):
        logger.debug(
            "Rejected activity media access for an activity the caller does not own",
            extra=core_logger.context(activity_id=activity_id, user_id=user_id),
        )
        raise core_exceptions.NotFoundError("Activity not found")


def _build_storage_key(activity_id: int, original_name: str | None) -> str:
    """Build a storage key for an uploaded media file.

    The original filename is reduced to its basename and its extension checked
    against the allow-list; the key itself is generated server-side, so a hostile
    filename is never used to address a blob nor echoed back.

    Args:
        activity_id: ID of the activity the media belongs to.
        original_name: Original ``UploadFile.filename`` value.

    Returns:
        A key of the form ``"{activity_id}_{uuid}{ext}"``. The ``{activity_id}_``
        prefix is what lets the deletion cleanup find every blob for an activity
        after its rows have cascaded away.

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


def _content_type_for(storage_key: str) -> str:
    """Return the media type implied by a storage key's extension.

    Derived from the server-generated key rather than the client's
    ``Content-Type`` header, which is unvalidated and would otherwise become the
    stored object's metadata (a ``.jpg`` uploaded as ``text/html``).

    Args:
        storage_key: The key the blob is stored under, carrying an extension
            already checked against :data:`_ALLOWED_MEDIA_EXTENSIONS`.

    Returns:
        An ``image/*`` media type.
    """
    extension = PurePosixPath(storage_key).suffix.lower().lstrip(".")
    # ``jpg`` is the only allowed extension whose media subtype is not the suffix.
    subtype = "jpeg" if extension == "jpg" else extension
    return f"image/{subtype}"


def _storage() -> platform_providers.StorageProvider:
    """Return the active platform's blob-storage provider."""
    return platform_runtime.get_active_platform().storage


def _cleanup_orphaned_blob(storage: platform_providers.StorageProvider, storage_key: str, activity_id: int) -> None:
    """Best-effort delete of a blob whose database row was never created.

    Args:
        storage: The storage provider the blob was saved through.
        storage_key: The key to remove.
        activity_id: The activity it was being attached to, for the log context.

    Returns:
        None.
    """
    try:
        storage.delete(activity_media_signing.MEDIA_STORAGE_AREA, storage_key)
    except Exception as storage_err:
        logger.warning(
            "Failed to clean up an orphaned activity media blob",
            extra=core_logger.context(activity_id=activity_id, storage_key=storage_key, reason=str(storage_err)),
        )


def _persist_media_bytes(
    activity_id: int,
    original_filename: str | None,
    data: bytes,
    db: Session,
) -> activity_media_contracts.ActivityMediaRecord:
    """Store validated image bytes, no-op'ing a byte-for-byte repeat.

    Shared by the multipart upload and server-side ingestion paths — both hand
    over already-validated bytes for one activity, and neither should create a
    second row for a photo already stored there (a retried upload, or a Strava
    bulk-export re-run reprocessing files it already imported).

    Args:
        activity_id: The activity to attach the media to.
        original_filename: Source filename, used only for its extension.
        data: Validated image bytes.
        db: Database session.

    Returns:
        The stored record — freshly created, or the existing one when the exact
        same bytes were already stored for this activity.

    Raises:
        UnsupportedMediaTypeError: For an unsupported extension.
        ConflictError: On a ``media_path`` collision (astronomically unlikely —
            the key is a server-generated UUID — so not a content duplicate).
    """
    content_hash = core_hashing.sha256_hex(data)
    existing = activity_media_crud.get_activity_media_by_content_hash(activity_id, content_hash, db)
    if existing is not None:
        logger.info(
            "Skipping re-store: identical media already stored for this activity",
            extra=core_logger.context(activity_id=activity_id, media_id=existing.id),
        )
        return existing

    storage_key = _build_storage_key(activity_id, original_filename)
    storage = _storage()
    storage.save(activity_media_signing.MEDIA_STORAGE_AREA, storage_key, data, _content_type_for(storage_key))

    try:
        return activity_media_crud.create_activity_media(activity_id, storage_key, db, content_hash=content_hash)
    except core_exceptions.ConflictError:
        # The pre-check above is read-then-write: a concurrent store of the same
        # bytes for this activity can race it. The unique (activity_id,
        # content_hash) index is what actually guarantees the no-op; losing that
        # race means the other caller stored it, which is the outcome this one
        # wanted too — return the winner rather than surfacing a conflict for
        # what the caller experiences as a successful store.
        winner = activity_media_crud.get_activity_media_by_content_hash(activity_id, content_hash, db)
        _cleanup_orphaned_blob(storage, storage_key, activity_id)
        if winner is None:
            raise
        return winner
    except core_exceptions.DomainError:
        _cleanup_orphaned_blob(storage, storage_key, activity_id)
        raise


def _to_read_model(
    record: activity_media_contracts.ActivityMediaRecord,
) -> activity_media_schema.ActivityMedia:
    """Resolve a stored record to the client-facing read model.

    The record→URL step lives here rather than in ``crud`` because addressing a
    blob is a storage/signing concern, not a persistence one — the persistence
    layer has no business knowing that a key becomes a signed route on local disk
    and a presigned URL on S3.

    Args:
        record: The persisted media record.

    Returns:
        The read model, with the servable URL resolved.
    """
    return activity_media_schema.ActivityMedia(
        id=record.id,
        activity_id=record.activity_id,
        media_type=record.media_type,
        url=activity_media_signing.media_url(record.media_path, record.activity_id, record.id),
    )


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
    if not activities_service.owns_activity(activity_id, user_id, db):
        logger.debug(
            "Listing activity media for an activity the caller does not own; returning empty",
            extra=core_logger.context(activity_id=activity_id, user_id=user_id),
        )
        return []
    records = activity_media_crud.get_media_for_activity(activity_id, db) or []
    logger.debug(
        "Listed activity media",
        extra=core_logger.context(activity_id=activity_id, user_id=user_id, count=len(records)),
    )
    return [_to_read_model(record) for record in records]


def read_activity_media_blob(activity_id: int, media_id: int, db: Session) -> tuple[bytes, str] | None:
    """Read one media blob for the token-gated serve route.

    Authorization is the signed token the caller already presented; this only
    resolves the record to its bytes and confirms it belongs to ``activity_id``,
    so a token minted for one activity's photo cannot be replayed under another
    activity's URL.

    Args:
        activity_id: The activity from the request path.
        media_id: The media record from the request path.
        db: Database session.

    Returns:
        A ``(data, content_type)`` tuple, or ``None`` when the record or its blob
        is missing, or the record belongs to a different activity.
    """
    media = activity_media_crud.get_activity_media_by_id(media_id, db)
    if media is None or media.activity_id != activity_id:
        return None

    data = _storage().get(activity_media_signing.MEDIA_STORAGE_AREA, media.media_path)
    if data is None:
        logger.warning(
            "Activity media row has no blob behind its storage key",
            extra=core_logger.context(activity_id=activity_id, media_id=media_id),
        )
        return None

    return data, _content_type_for(media.media_path)


def store_activity_media(
    activity_id: int,
    user_id: int,
    file: UploadFile,
    db: Session,
) -> activity_media_schema.ActivityMedia:
    """Persist an uploaded image and register it against an activity.

    The upload is magic-number and size validated before any bytes are stored,
    then written through the storage provider under a server-generated key. If
    the database row cannot be created the blob is removed again, so a failed
    upload leaves nothing behind.

    Args:
        activity_id: The activity to attach the media to.
        user_id: The authenticated user, who must own the activity.
        file: The uploaded image.
        db: Database session.

    Returns:
        The created media record, carrying its signed servable URL. The same
        record is returned, without writing anything new, when the exact same
        bytes are already stored for this activity.

    Raises:
        NotFoundError: When the activity is not the user's.
        UnsupportedMediaTypeError: For an unsupported extension.
        ConflictError: On a duplicate key.
    """
    _require_owned_activity(activity_id, user_id, db)

    # SafeUploads validates magic number and size before anything is stored.
    # Callers run on a worker thread (the route is synchronous), so the blocking
    # read never touches the event loop.
    data = core_file_uploads.read_validated_upload_sync(file, kind=core_file_uploads.UploadKind.IMAGE)
    created = _persist_media_bytes(activity_id, file.filename, data, db)

    logger.info(
        "Stored activity media",
        extra=core_logger.context(activity_id=activity_id, user_id=user_id, media_id=created.id),
    )
    return _to_read_model(created)


def store_activity_media_bytes(
    activity_id: int,
    original_filename: str | None,
    data: bytes,
    db: Session,
) -> activity_media_contracts.ActivityMediaRecord:
    """Register already-validated image bytes as media for an activity.

    The server-side ingestion counterpart of :func:`store_activity_media`, for
    bytes that did not arrive as a multipart upload (a Strava bulk export's
    sidecar photos). Callers own the validation — they hold the file, not an
    ``UploadFile`` — but everything after that (the server-generated key, the
    storage area, the row) stays here, so there is one definition of what a
    stored activity media is.

    No ownership check: the caller is a server-side import that just created the
    activity, not a request acting on someone else's data.

    Args:
        activity_id: The activity to attach the media to.
        original_filename: The source filename, used only for its extension.
        data: The validated image bytes.
        db: Database session.

    Returns:
        The stored record — freshly created, or the existing one when a
        bulk-import re-run hands back a photo already stored for this activity.

    Raises:
        UnsupportedMediaTypeError: For an unsupported extension.
    """
    created = _persist_media_bytes(activity_id, original_filename, data, db)
    logger.info(
        "Stored activity media from a server-side import",
        extra=core_logger.context(activity_id=activity_id, media_id=created.id),
    )
    return created


def delete_activity_media(activity_id: int, media_id: int, user_id: int, db: Session) -> None:
    """Delete one of the user's media records and its stored blob.

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

    if media.media_path:
        # Best-effort: the row is the source of truth, and a stray blob is
        # harmless now that nothing serves it without a signed token.
        try:
            _storage().delete(activity_media_signing.MEDIA_STORAGE_AREA, media.media_path)
        except Exception as storage_err:
            logger.warning(
                "Failed to remove the stored blob for a deleted activity media record",
                extra=core_logger.context(media_id=media_id, reason=str(storage_err)),
            )

    logger.info(
        "Deleted activity media",
        extra=core_logger.context(activity_id=activity_id, media_id=media_id, user_id=user_id),
    )


def delete_media_files_for_activity(activity_id: int) -> int:
    """Remove every stored media blob belonging to one activity.

    Used by the ``activity.deleted`` cleanup subscriber. It works from the
    activity id alone and never touches the database, which is the only thing
    that *can* work here: ``activity_media`` rows are ``ON DELETE CASCADE``, so by
    the time the event is handled the rows carrying the storage key are already
    gone. Keys are ``{activity_id}_{uuid}{ext}``, so the id is enough to list them
    back off the provider.

    Idempotent, and safe to run for an activity that never had media.

    Args:
        activity_id: The deleted activity whose media blobs to remove.

    Returns:
        The number of blobs removed.
    """
    storage = _storage()
    # ``activity_id`` is an int, so the prefix carries no metacharacters. The
    # trailing underscore keeps activity 42 from matching activity 421's keys.
    prefix = f"{activity_id}_"

    removed = 0
    for key in storage.list_keys(activity_media_signing.MEDIA_STORAGE_AREA, prefix):
        try:
            storage.delete(activity_media_signing.MEDIA_STORAGE_AREA, key)
            removed += 1
        except Exception as storage_err:
            logger.warning(
                "Failed to remove an activity media blob",
                extra=core_logger.context(activity_id=activity_id, storage_key=key, reason=str(storage_err)),
            )

    if removed:
        logger.info(
            "Removed media blobs for a deleted activity",
            extra=core_logger.context(activity_id=activity_id, removed=removed),
        )
    return removed
