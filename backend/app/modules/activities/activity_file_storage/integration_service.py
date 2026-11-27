"""Public operations for retained activity source files.

The surface ``activity_ingestion``, the profile export and import, reprocess and account erasure call. A file is a
row (``activity_files``) plus a blob under the activity-files area; the activity core only holds the row's opaque id
(``activities.file_id``), so staging and attaching are arranged by the caller above both: stage the file, store the
activity with the file's id, attach in the same transaction.

An activity whose file was stored before rows existed has no ``file_id``: :func:`read_file` and
:func:`delete_legacy_activity_file` address it by activity id until those files are adopted. There is no servable
URL: the retained file is only consumed in-process (reprocess, profile export) and on cleanup, never served.
"""

import uuid
from collections.abc import Sequence

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import modules.activities.activity_file_storage.contracts as activity_file_storage_contracts
import modules.activities.activity_file_storage.files as activity_file_storage_files
import modules.activities.activity_file_storage.service as activity_file_storage_service


def stage_file(
    user_id: uuid.UUID,
    sha256: str,
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> activity_file_storage_contracts.StagedFile:
    """Record a user's file and store its blob, ready for an activity to attach it.

    Commits its own short transaction for the row before it writes the blob, so the caller's session is not used
    and none is open across the storage call. Bytes the user already retained share the existing row.

    Args:
        user_id: The owner.
        sha256: Hex SHA-256 of ``data``.
        extension: The file's extension, e.g. ``".fit"``.
        data: The raw (already decompressed) file bytes.
        storage: The blob-storage provider.

    Returns:
        The file, and whether this call created its row.
    """
    return activity_file_storage_service.stage_file(user_id, sha256, extension, data, storage)


def mark_attached(file_id: uuid.UUID, db: Session) -> None:
    """Stage a file row as referenced by the activity the caller stores in the same transaction.

    The caller commits.

    Args:
        file_id: The file row.
        db: Database session.

    Raises:
        ProcessingError: When the row is gone or being deleted, so the caller's job runs again and stages a new row.
    """
    activity_file_storage_service.mark_attached(file_id, db)


def release_unattached(file_id: uuid.UUID, storage: platform_providers.StorageProvider) -> None:
    """Remove a row the caller created and no activity referenced, with its blob.

    Commits its own short transactions and deletes the blob with no session open.

    Args:
        file_id: The file row.
        storage: The blob-storage provider.
    """
    activity_file_storage_service.release_unattached(file_id, storage)


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
    return activity_file_storage_service.resolve_refs(file_ids, db)


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
    return activity_file_storage_service.read_file(activity_id, ref, storage)


def delete_legacy_activity_file(
    activity_id: uuid.UUID,
    storage: platform_providers.StorageProvider,
) -> None:
    """Delete the file an activity without a file row stored under its own id.

    Idempotent: an activity with no such file is left as it is.

    Args:
        activity_id: The activity.
        storage: The blob-storage provider.
    """
    activity_file_storage_files.delete_legacy_files(activity_id, storage)


def erase_user_files(user_id: uuid.UUID, storage: platform_providers.StorageProvider) -> None:
    """Delete every retained file a user has, with its row, for account erasure.

    Commits its own short transactions and deletes blobs with no session open.

    Args:
        user_id: The user.
        storage: The blob-storage provider.
    """
    activity_file_storage_service.erase_user_files(user_id, storage)
