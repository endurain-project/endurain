"""Application logic for activity media (photos attached to an activity).

Owns everything that is not persistence: the ownership checks, the
server-generated storage key, writing the validated upload through the platform
``StorageProvider``, and removing the blob when the record goes away. ``crud.py``
is pure persistence and the router is a thin HTTP adapter, so the ownership rule
lives here once.

Blobs go through the ``StorageProvider``, the same as thumbnails and retained
source files: photos survive on object storage and are reachable only through
the token-gated route, not pinned to one node's disk.
"""

import re
import uuid
from pathlib import PurePosixPath

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import core.pagination as core_pagination
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.schema as activity_media_schema
import modules.activities.activity_media.signing as activity_media_signing
import modules.activities.orphan_sweep as activities_orphan_sweep

logger = core_logger.get_logger(__name__)

# Allow-list of safe image extensions for activity media uploads. The upload is
# also magic-number validated by safeuploads; this only bounds the extension we
# are willing to record in a storage key.
_ALLOWED_MEDIA_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"})

# A stored key is ``{activity_id}_{suffix}``; ``suffix`` is a flat file name.
_MEDIA_KEY_PATTERN = re.compile(r"(?P<activity_id>\d+)_(?P<suffix>[^/\\]+)")


def _key_prefix(activity_id: int) -> str:
    """Return the prefix shared by every storage key of one activity.

    ``activity_id`` is an int, so the prefix carries no metacharacters. The
    trailing underscore keeps activity 42 from matching activity 421's keys.

    Args:
        activity_id: ID of the activity the media belongs to.

    Returns:
        The key prefix, ``"{activity_id}_"``.
    """
    return f"{activity_id}_"


def _media_key(activity_id: int, suffix: str) -> str:
    """Return the storage key for ``suffix`` under an activity.

    Args:
        activity_id: ID of the activity the media belongs to.
        suffix: The flat file name following the activity prefix.

    Returns:
        The storage key, ``"{activity_id}_{suffix}"``.
    """
    return f"{_key_prefix(activity_id)}{suffix}"


def _require_owned_activity(activity_id: int, requester_user_id: int, db: Session) -> None:
    """Raise :class:`NotFoundError` unless ``requester_user_id`` owns ``activity_id``.

    "Not found" rather than "forbidden" so a caller cannot use the media endpoints
    to probe which activity ids exist.

    Args:
        activity_id: The activity the media belongs to.
        requester_user_id: The authenticated user.
        db: Database session.

    Raises:
        NotFoundError: When the activity does not exist or is not owned by the
            user.
    """
    if not activity_integration.owns_activity(activity_id, requester_user_id, db):
        logger.debug(
            "Rejected activity media access for an activity the caller does not own",
            extra=core_logger.context(activity_id=activity_id, requester_user_id=requester_user_id),
        )
        raise core_exceptions.NotFoundError("Activity not found")


def _build_storage_key(activity_id: int, original_name: str | None) -> str:
    """Build a storage key for an uploaded media file.

    The original filename is reduced to its basename and its extension checked
    against the allow-list; the key itself is generated server-side, so a hostile
    filename is never used to address a blob nor echoed back.

    Args:
        activity_id: ID of the activity the media belongs to.
        original_name: Original upload filename.

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

    return _media_key(activity_id, f"{uuid.uuid4().hex}{extension}")


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


def _cleanup_orphaned_blob(storage: platform_providers.StorageProvider, storage_key: str, activity_id: int) -> None:
    """Best-effort delete of a blob whose database row was never created.

    Args:
        storage: The storage provider the blob was saved through.
        storage_key: The key to remove.
        activity_id: The activity it was being attached to, for the log context.
    """
    try:
        storage.delete(activity_media_signing.MEDIA_STORAGE_AREA, storage_key)
    except Exception as storage_err:
        logger.warning(
            "Failed to clean up an orphaned activity media blob",
            exc_info=storage_err,
            extra=core_logger.context(activity_id=activity_id, storage_key=storage_key),
        )


def _persist_media_bytes(
    activity_id: int,
    original_filename: str | None,
    data: bytes,
    storage: platform_providers.StorageProvider,
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
        storage: The blob-storage provider.
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
        logger.debug(
            "Skipping re-store: identical media already stored for this activity",
            extra=core_logger.context(activity_id=activity_id, media_id=existing.id),
        )
        return existing

    storage_key = _build_storage_key(activity_id, original_filename)
    storage.save(activity_media_signing.MEDIA_STORAGE_AREA, storage_key, data, _content_type_for(storage_key))

    try:
        record = activity_media_crud.create_activity_media(activity_id, storage_key, db, content_hash=content_hash)
        db.commit()
        return record
    except core_exceptions.ConflictError:
        # The failed flush leaves the session unusable until it is rolled back,
        # and the winner lookup below needs it.
        db.rollback()
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
    except Exception:
        # Any failure to record the row (a domain error, a failed commit) leaves
        # the blob no row names.
        _cleanup_orphaned_blob(storage, storage_key, activity_id)
        raise


def _to_read_model(
    record: activity_media_contracts.ActivityMediaRecord,
) -> activity_media_schema.ActivityMediaRead:
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
    return activity_media_schema.ActivityMediaRead(
        id=record.id,
        activity_id=record.activity_id,
        media_type=record.media_type,
        url=activity_media_signing.media_url(record.media_path, record.activity_id, record.id),
    )


def list_activity_media(
    activity_id: int,
    requester_user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_CHILD_NUM_RECORDS,
) -> activity_media_schema.ActivityMediaPage:
    """List one page of the media attached to one of the user's activities.

    Args:
        activity_id: The activity whose media to list.
        requester_user_id: The authenticated user.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page envelope, empty when the activity is not the user's or has no
        media. "You cannot see it" and "there is none" are deliberately
        indistinguishable, so the endpoint cannot be used to probe which
        activity ids exist.
    """
    if not activity_integration.owns_activity(activity_id, requester_user_id, db):
        logger.debug(
            "Listing activity media for an activity the caller does not own; returning empty",
            extra=core_logger.context(activity_id=activity_id, requester_user_id=requester_user_id),
        )
        return activity_media_schema.ActivityMediaPage.build([], 0, page_number, num_records)
    records = activity_media_crud.get_media_for_activity(
        activity_id, db, page_number=page_number, num_records=num_records
    )
    total = activity_media_crud.count_media_for_activity(activity_id, db)
    logger.debug(
        "Listed activity media",
        extra=core_logger.context(activity_id=activity_id, requester_user_id=requester_user_id, count=len(records)),
    )
    return activity_media_schema.ActivityMediaPage.build(
        [_to_read_model(record) for record in records], total, page_number, num_records
    )


def read_activity_media_blob(
    activity_id: int,
    media_id: int,
    token: str,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> tuple[bytes, str]:
    """Read one media blob for the token-gated serve route.

    Authorization is the signed token the caller presented: it is bound to the
    media id, and the record must also belong to ``activity_id``, so a token
    minted for one activity's photo cannot be replayed under another activity's
    URL.

    Args:
        activity_id: The activity from the request path.
        media_id: The media record from the request path.
        token: The signed access token minted at serialization time.
        storage: The blob-storage provider.
        db: Database session.

    Returns:
        A ``(data, content_type)`` tuple.

    Raises:
        AccessConcealedError: When the token is invalid or forged.
        NotFoundError: When the record does not
            belong to ``activity_id``, or no blob exists. A 404 rather than 403
            avoids confirming the resource to an unauthorized caller.
    """
    if not activity_media_signing.verify_media_token(media_id, token):
        # Security-relevant: either a forged token or one replayed against a
        # different media id. Logged at warning so a probing pattern is visible.
        logger.warning(
            "Rejected an activity media request with an invalid signed token",
            extra=core_logger.context(activity_id=activity_id, media_id=media_id),
        )
        raise core_exceptions.AccessConcealedError("Activity media not found")

    media = activity_media_crud.get_activity_media_by_id(media_id, db)
    if media is None or media.activity_id != activity_id:
        raise core_exceptions.NotFoundError("Activity media not found")

    data = storage.get(activity_media_signing.MEDIA_STORAGE_AREA, media.media_path)
    if data is None:
        logger.warning(
            "Activity media row has no blob behind its storage key",
            extra=core_logger.context(activity_id=activity_id, media_id=media_id),
        )
        raise core_exceptions.NotFoundError("Activity media not found")

    return data, _content_type_for(media.media_path)


def store_activity_media(
    activity_id: int,
    requester_user_id: int,
    original_filename: str | None,
    data: bytes,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> activity_media_schema.ActivityMediaRead:
    """Persist an uploaded image and register it against an activity.

    The caller has already validated the bytes (magic number and size). They are
    written through the storage provider under a server-generated key. If the
    database row cannot be created the blob is removed again, so a failed upload
    leaves nothing behind.

    Args:
        activity_id: The activity to attach the media to.
        requester_user_id: The authenticated user, who must own the activity.
        original_filename: The uploaded filename, used only for its extension.
        data: The validated image bytes.
        storage: The blob-storage provider.
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
    _require_owned_activity(activity_id, requester_user_id, db)

    created = _persist_media_bytes(activity_id, original_filename, data, storage, db)

    logger.info(
        "Stored activity media",
        extra=core_logger.context(activity_id=activity_id, requester_user_id=requester_user_id, media_id=created.id),
    )
    return _to_read_model(created)


def store_activity_media_bytes(
    activity_id: int,
    original_filename: str | None,
    data: bytes,
    storage: platform_providers.StorageProvider,
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
        storage: The blob-storage provider.
        db: Database session.

    Returns:
        The stored record — freshly created, or the existing one when a
        bulk-import re-run hands back a photo already stored for this activity.

    Raises:
        UnsupportedMediaTypeError: For an unsupported extension.
    """
    created = _persist_media_bytes(activity_id, original_filename, data, storage, db)
    logger.info(
        "Stored activity media from a server-side import",
        extra=core_logger.context(activity_id=activity_id, media_id=created.id),
    )
    return created


def delete_activity_media(
    activity_id: int,
    media_id: int,
    requester_user_id: int,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> None:
    """Delete one of the user's media records and its stored blob.

    Args:
        activity_id: The activity the media must belong to, taken from the route
            path. Checked so a media id cannot be deleted through an unrelated
            activity's URL.
        media_id: The media record to delete.
        requester_user_id: The authenticated user, who must own the owning activity.
        storage: The blob-storage provider.
        db: Database session.

    Raises:
        NotFoundError: When the media does not exist, does not belong to
            ``activity_id``, or its activity is not the user's.
    """
    media = activity_media_crud.get_activity_media_by_id(media_id, db)
    if media is None or media.activity_id != activity_id:
        raise core_exceptions.NotFoundError("Activity media not found")

    _require_owned_activity(media.activity_id, requester_user_id, db)

    activity_media_crud.delete_activity_media(media_id, db)
    db.commit()

    if media.media_path:
        # Best-effort: the row is the source of truth, and a stray blob is
        # harmless because nothing serves it without a signed token.
        try:
            storage.delete(activity_media_signing.MEDIA_STORAGE_AREA, media.media_path)
        except Exception as storage_err:
            logger.warning(
                "Failed to remove the stored blob for a deleted activity media record",
                exc_info=storage_err,
                extra=core_logger.context(media_id=media_id),
            )

    logger.info(
        "Deleted activity media",
        extra=core_logger.context(activity_id=activity_id, media_id=media_id, requester_user_id=requester_user_id),
    )


def delete_media_files_for_activity(activity_id: int, storage: platform_providers.StorageProvider) -> int:
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
        storage: The blob-storage provider.

    Returns:
        The number of blobs removed.
    """
    removed = 0
    for key in storage.list_keys(activity_media_signing.MEDIA_STORAGE_AREA, _key_prefix(activity_id)):
        try:
            storage.delete(activity_media_signing.MEDIA_STORAGE_AREA, key)
            removed += 1
        except Exception as storage_err:
            logger.warning(
                "Failed to remove an activity media blob",
                exc_info=storage_err,
                extra=core_logger.context(activity_id=activity_id, storage_key=key),
            )

    if removed:
        logger.info(
            "Removed media blobs for a deleted activity",
            extra=core_logger.context(activity_id=activity_id, removed=removed),
        )
    return removed


def list_media_blobs(activity_id: int, storage: platform_providers.StorageProvider) -> list[tuple[str, bytes]]:
    """Return every readable media blob attached to an activity.

    Best-effort for the profile export: a storage failure listing the keys yields
    an empty result, and a blob that cannot be read is skipped, so one bad object
    never aborts the whole export.

    Args:
        activity_id: The activity whose blobs to read.
        storage: The blob-storage provider.

    Returns:
        ``(storage_key, bytes)`` pairs for the blobs that could be read.
    """
    try:
        keys = storage.list_keys(activity_media_signing.MEDIA_STORAGE_AREA, _key_prefix(activity_id))
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
    """Restore one exported media blob under an activity and return its key.

    Args:
        activity_id: The activity the blob now belongs to.
        suffix: The exported file name without its extension.
        extension: The exported file's extension, including the dot.
        data: The already-validated image bytes.
        storage: The blob-storage provider.

    Returns:
        The storage key the blob was saved under.
    """
    key = _media_key(activity_id, f"{suffix}{extension}")
    storage.save(activity_media_signing.MEDIA_STORAGE_AREA, key, data)
    return key


def rekey_media_path(old_key: str, new_activity_id: int) -> str | None:
    """Return an exported media key re-addressed to a restored activity.

    Args:
        old_key: The ``media_path`` recorded in a profile archive.
        new_activity_id: The activity the record is being restored onto.

    Returns:
        The key under the new activity, or ``None`` when ``old_key`` is not a
        flat ``{activity_id}_{suffix}`` key (the archive is untrusted).
    """
    match = _MEDIA_KEY_PATTERN.fullmatch(old_key)
    if match is None:
        return None
    return _media_key(new_activity_id, match.group("suffix"))


def _activity_id_of_media_key(key: str) -> int | None:
    """Return the activity id a flat ``{activity_id}_{suffix}`` media key names.

    Args:
        key: A storage key in the media area.

    Returns:
        The activity id, or ``None`` when the key does not match the layout.
    """
    match = _MEDIA_KEY_PATTERN.fullmatch(key)
    return int(match.group("activity_id")) if match else None


def sweep_orphaned_media(storage: platform_providers.StorageProvider, db: Session) -> int:
    """Delete media blobs that no longer belong to anything.

    The storage-side net for the cleanup paths. A blob is swept when its activity
    is gone (a dropped ``activity.deleted`` event, since the media rows cascade
    with the activity) or when no media row names it (a failed best-effort delete
    after the row was removed). Only a scan of the area finds either.

    Args:
        storage: The blob-storage provider.
        db: Database session.

    Returns:
        The number of blobs deleted.
    """
    removed = activities_orphan_sweep.sweep_orphaned_blobs(
        storage,
        activity_media_signing.MEDIA_STORAGE_AREA,
        lambda ids: activity_integration.filter_existing_activity_ids(ids, db),
        _activity_id_of_media_key,
    )
    return removed + activities_orphan_sweep.sweep_unreferenced_blobs(
        storage,
        activity_media_signing.MEDIA_STORAGE_AREA,
        lambda keys: activity_media_crud.get_existing_media_paths(keys, db),
    )
