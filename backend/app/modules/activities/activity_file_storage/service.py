"""Lifecycle of the retained activity source files: stage, attach, release, sweep and erase.

A file row moves ``pending`` (row and blob written, no activity yet) to ``attached`` (an activity references it) to
``deleting`` (the blob, then the row, are being removed). Every step that touches storage runs with no database
session open: a short transaction decides, the blob call follows, and a second short transaction records it.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.contracts as activity_file_storage_contracts
import modules.activities.activity_file_storage.crud as activity_file_storage_crud
import modules.activities.activity_file_storage.files as activity_file_storage_files

logger = core_logger.get_logger(__name__)

_AREA = activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA
_State = activity_file_storage_constants.ActivityFileState


def stage_file(
    user_id: uuid.UUID,
    sha256: str,
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> activity_file_storage_contracts.StagedFile:
    """Record a user's file and store its blob, ready for an activity to attach it.

    The row is committed in its own short transaction before the blob is written, so no session is open across the
    storage call. Bytes the user already retained take the existing row and, when it is attached, write nothing.

    Args:
        user_id: The owner.
        sha256: Hex SHA-256 of ``data``.
        extension: The file's extension, e.g. ``".fit"``.
        data: The raw (already decompressed) file bytes.
        storage: The blob-storage provider.

    Returns:
        The file, and whether this call created its row.
    """
    with core_database.SessionLocal() as db:
        ref, state, created = activity_file_storage_crud.take_live_file(user_id, sha256, extension, len(data), db)
        db.commit()
    if state != _State.ATTACHED:
        storage.save(_AREA, ref.storage_key, data)
    logger.debug(
        "Staged the activity source file",
        extra=core_logger.context(file_id=ref.file_id, user_id=user_id, created=created),
    )
    return activity_file_storage_contracts.StagedFile(ref=ref, created=created)


def stage_adoption(
    activity_id: uuid.UUID, user_id: uuid.UUID, sha256: str, extension: str, size_bytes: int, db: Session
) -> activity_file_storage_contracts.StagedFile:
    """Stage a row for the file an activity stored before rows existed, keyed by the blob it already has.

    Writes no blob. Bytes the user already retained take the existing row, so the caller points the activity at it
    and, once committed, settles the activity's own blob with :func:`settle_adopted_file`. The caller commits.

    Args:
        activity_id: The activity whose legacy blob is adopted.
        user_id: The owner.
        sha256: Hex SHA-256 of the file.
        extension: The file's extension, e.g. ``".fit"``.
        size_bytes: The file's size.
        db: Database session.

    Returns:
        The file, and whether this call created its row.
    """
    ref, _state, created = activity_file_storage_crud.take_live_file(
        user_id,
        sha256,
        extension,
        size_bytes,
        db,
        storage_key=activity_file_storage_files.legacy_file_key(activity_id, extension),
    )
    return activity_file_storage_contracts.StagedFile(ref=ref, created=created)


def settle_adopted_file(
    activity_id: uuid.UUID,
    staged: activity_file_storage_contracts.StagedFile,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> None:
    """Resolve the activity's own legacy blob once its adoption committed, with no session open.

    A row this adoption created names that blob, so there is nothing to do. A row shared with other bytes' owners
    names another blob: it is written from ``data`` when it has none (an upload that crashed before writing it), and
    the activity's own blob, which holds the same bytes, is deleted. A failure raises, and the activity, still
    adopted, leaves its blob for the ``processed/`` sweep.

    Args:
        activity_id: The adopted activity.
        staged: What :func:`stage_adoption` returned.
        data: The file's bytes.
        storage: The blob-storage provider.
    """
    own_key = activity_file_storage_files.legacy_file_key(activity_id, staged.ref.extension)
    if staged.created or own_key == staged.ref.storage_key:
        return
    if storage.stat(_AREA, staged.ref.storage_key) is None:
        logger.warning(
            "The shared activity source file had no blob; it is written from the adopted one",
            extra=core_logger.context(file_id=staged.ref.file_id),
        )
        storage.save(_AREA, staged.ref.storage_key, data)
    storage.delete(_AREA, own_key)
    logger.debug(
        "Collapsed a legacy activity source file into the row of the same bytes",
        extra=core_logger.context(activity_id=activity_id, file_id=staged.ref.file_id),
    )


def live_processed_keys(keys: Sequence[str], db: Session) -> set[str]:
    """Return which ``processed/`` keys must be kept: a row names them, or their top-level activity has no file row.

    A key that is not ``processed/{activity id}{extension}`` is kept, as it is not this sweep's to judge.

    Args:
        keys: Storage keys under ``processed/``.
        db: Database session.

    Returns:
        The subset to keep.
    """
    named = activity_file_storage_crud.get_named_keys(keys, db)
    owners = {key: activity_file_storage_files.activity_id_of_processed_key(key) for key in keys if key not in named}
    owner_ids = [owner for owner in owners.values() if owner is not None]
    # A leg's file is kept under its multisport activity, so a leg's own copy is left over from a regroup.
    unadopted = activity_integration.filter_unadopted_activity_ids(owner_ids, db)
    return named | {key for key, owner in owners.items() if owner is None or owner in unadopted}


def mark_attached(file_id: uuid.UUID, db: Session) -> None:
    """Stage a file row as referenced by the activity the caller is storing; the caller commits.

    Args:
        file_id: The file row.
        db: Database session, in the transaction that stores the activity.

    Raises:
        ProcessingError: When the row is gone or being deleted, so the caller's job runs again and stages a new row.
    """
    if not activity_file_storage_crud.mark_attached(file_id, db):
        logger.debug("The activity source file row is no longer live", extra=core_logger.context(file_id=file_id))
        raise core_exceptions.ProcessingError()


def release_unattached(file_id: uuid.UUID, storage: platform_providers.StorageProvider) -> None:
    """Remove a row this caller created and no activity ended up referencing, with its blob.

    Args:
        file_id: The file row.
        storage: The blob-storage provider.
    """
    with core_database.SessionLocal() as db:
        activity_file_storage_crud.mark_deleting([file_id], _State.PENDING, db)
        db.commit()
    logger.debug("Released an unattached activity source file", extra=core_logger.context(file_id=file_id))
    delete_deleting_file(file_id, storage)


def release_unreferenced(file_id: uuid.UUID, storage: platform_providers.StorageProvider) -> None:
    """Remove a file whose activity was deleted, unless another activity still references it.

    The ``activity.deleted`` cleanup. Raises on a storage failure so the durable runner retries, and a retry that finds
    the row already ``deleting`` finishes the removal.

    Args:
        file_id: The file row the deleted activity referenced.
        storage: The blob-storage provider.
    """
    with core_database.SessionLocal() as db:
        marked = _mark_unreferenced([file_id], db)
        db.commit()
    logger.debug(
        "Released the activity source file of a deleted activity",
        extra=core_logger.context(file_id=file_id, unreferenced=bool(marked)),
    )
    delete_deleting_file(file_id, storage)


def delete_deleting_file(file_id: uuid.UUID, storage: platform_providers.StorageProvider) -> None:
    """Delete the blob of a row that is ``deleting``, then the row.

    Args:
        file_id: The file row; one that is gone or in another state is left alone.
        storage: The blob-storage provider.
    """
    with core_database.SessionLocal() as db:
        ref = activity_file_storage_crud.get_deleting_ref(file_id, db)
    if ref is None:
        logger.debug("No activity source file to delete", extra=core_logger.context(file_id=file_id))
        return
    storage.delete(_AREA, ref.storage_key)
    with core_database.SessionLocal() as db:
        activity_file_storage_crud.delete_deleting([file_id], db)
        db.commit()
    logger.debug("Deleted the activity source file", extra=core_logger.context(file_id=file_id))


def _mark_unreferenced(file_ids: Sequence[uuid.UUID], db: Session) -> list[uuid.UUID]:
    """Stage ``deleting`` for the ``attached`` rows no activity references.

    The rows are locked first, so an upload that is attaching to one finishes before the references are read.

    Args:
        file_ids: The file rows.
        db: Database session; the caller commits.

    Returns:
        The ids that moved.
    """
    attached = activity_file_storage_crud.lock_attached(file_ids, db)
    referenced = activity_integration.filter_referenced_file_ids(attached, db)
    unreferenced = [file_id for file_id in attached if file_id not in referenced]
    activity_file_storage_crud.mark_deleting(unreferenced, _State.ATTACHED, db)
    return unreferenced


def sweep(storage: platform_providers.StorageProvider) -> int:
    """Resolve the rows a crash or a lost event left behind, with no storage listing.

    Moves ``pending`` rows and unreferenced ``attached`` rows older than a day to ``deleting``, then deletes the blob
    and the row of every ``deleting`` row. A blob the storage cannot delete is logged and its row stays for the
    next run.

    Args:
        storage: The blob-storage provider.

    Returns:
        How many files were deleted.
    """
    cutoff = datetime.now(UTC) - activity_file_storage_constants.SWEEP_MIN_AGE
    batch = activity_file_storage_constants.BATCH_SIZE
    while True:
        with core_database.SessionLocal() as db:
            moved = activity_file_storage_crud.claim_stale_pending(cutoff, batch, db)
            db.commit()
        if moved < batch:
            break
    after_id: uuid.UUID | None = None
    while True:
        with core_database.SessionLocal() as db:
            page = activity_file_storage_crud.list_attached_before(cutoff, after_id, batch, db)
            # Only the rows no activity references are locked, and their references read again under the lock.
            referenced = activity_integration.filter_referenced_file_ids(page, db)
            _mark_unreferenced([file_id for file_id in page if file_id not in referenced], db)
            db.commit()
        if len(page) < batch:
            break
        after_id = page[-1]
    removed = _delete_deleting_files(storage)
    logger.debug("Swept the retained activity source files", extra=core_logger.context(removed=removed))
    return removed


def _delete_deleting_files(storage: platform_providers.StorageProvider) -> int:
    """Delete the blob and then the row of every ``deleting`` row, a page at a time.

    Args:
        storage: The blob-storage provider.

    Returns:
        How many files were deleted.
    """
    batch = activity_file_storage_constants.BATCH_SIZE
    removed = 0
    after_id: uuid.UUID | None = None
    while True:
        with core_database.SessionLocal() as db:
            page = activity_file_storage_crud.list_deleting(after_id, batch, db)
        deleted: list[uuid.UUID] = []
        for ref in page:
            try:
                storage.delete(_AREA, ref.storage_key)
            except platform_providers.StorageBackendUnavailableError as err:
                logger.warning(
                    "Could not delete a retained activity file; it is retried",
                    exc_info=err,
                    extra=core_logger.context(file_id=ref.file_id),
                )
            else:
                deleted.append(ref.file_id)
        with core_database.SessionLocal() as db:
            activity_file_storage_crud.delete_deleting(deleted, db)
            db.commit()
        removed += len(deleted)
        if len(page) < batch:
            return removed
        after_id = page[-1].file_id


def erase_user_files(user_id: uuid.UUID, storage: platform_providers.StorageProvider) -> None:
    """Delete every retained file a user has, in whatever state, with its row.

    Account erasure runs it once the user's activities are gone and before the user row is deleted. A storage
    failure propagates so the deletion job runs again.

    Args:
        user_id: The user.
        storage: The blob-storage provider.

    """
    removed = 0
    while True:
        with core_database.SessionLocal() as db:
            refs = activity_file_storage_crud.list_user_files(user_id, activity_file_storage_constants.BATCH_SIZE, db)
        if not refs:
            logger.debug(
                "Erased the retained files of a user", extra=core_logger.context(user_id=user_id, count=removed)
            )
            return
        for ref in refs:
            storage.delete(_AREA, ref.storage_key)
        with core_database.SessionLocal() as db:
            activity_file_storage_crud.delete_files([ref.file_id for ref in refs], db)
            db.commit()
        removed += len(refs)


def resolve_refs(
    file_ids: Sequence[uuid.UUID], db: Session
) -> dict[uuid.UUID, activity_file_storage_contracts.ActivityFileRef]:
    """Return the references of the given file rows.

    Args:
        file_ids: The file rows.
        db: Database session.

    Returns:
        The reference by id; a missing row is absent.
    """
    return activity_file_storage_crud.get_refs(file_ids, db)


def read_file(
    activity_id: uuid.UUID,
    ref: activity_file_storage_contracts.ActivityFileRef | None,
    storage: platform_providers.StorageProvider,
) -> tuple[str, bytes] | None:
    """Read an activity's retained source file.

    Args:
        activity_id: The activity.
        ref: The file row the activity references, or ``None`` for an activity that has none, whose file is probed
            under its own id.
        storage: The blob-storage provider.

    Returns:
        The file's ``(extension, data)``, or ``None`` when the activity has no retained file.
    """
    if ref is None:
        return activity_file_storage_files.read_legacy_file(activity_id, storage)
    data = storage.get(_AREA, ref.storage_key)
    if data is None:
        logger.warning("A retained activity file has no blob", extra=core_logger.context(file_id=ref.file_id))
        return None
    return ref.extension, data
