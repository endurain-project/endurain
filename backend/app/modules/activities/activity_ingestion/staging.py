"""Node-independent staging for bulk-import files.

Bulk import starts from files a user drops into a directory on the server, but
the work is done by a durable job that any worker in the fleet may claim. Putting
a **filesystem path** in the job payload therefore only worked when the worker
happened to run on the node holding that path: in the ``distributed`` profile the
claiming worker cannot see the file, so the job fails, retries onto another node
that also cannot see it, and dead-letters — while the route has already answered
202.

Staging closes that gap. The request thread, which *can* see the dropped file,
copies its bytes into the platform ``StorageProvider`` and puts the resulting
**key** in the payload. Any worker can then fetch the bytes regardless of where
it runs, which is the same shape the activity-media and user-photo paths already
use.

The parsers work on file paths (and ``.gz`` handling rewrites those paths), so
the worker materialises the blob back to a temp file rather than the pipeline
being rewritten to take bytes. The temp file is written under the *original*
filename because the pipeline derives meaning from it — the Strava export's
``activities.csv`` is keyed by filename, and the Garmin activity id is parsed out
of it.
"""

import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import core.logger as core_logger
import infra.runtime as platform_runtime

logger = core_logger.get_logger(__name__)

# Blobs awaiting import, and the ones whose job exhausted its retries.
BULK_IMPORT_STORAGE_AREA = "bulk_import"
BULK_IMPORT_ERROR_STORAGE_AREA = "bulk_import_errors"


def _storage():
    """Return the active platform's storage provider."""
    return platform_runtime.get_active_platform().storage


def build_key(user_id: int, filename: str) -> str:
    """Mint a storage key for one staged bulk-import file.

    Flat and prefixed with the owner, matching the activity-media convention:
    the local backend's ``list_keys`` does not recurse, so a nested key would be
    unlistable and any future orphan sweep would silently find nothing.

    A random component is included because two imports may legitimately queue the
    same filename, and the second must not overwrite the first while it waits.

    Args:
        user_id: Owner of the import.
        filename: The dropped file's name, used only for its extension.

    Returns:
        The storage key.
    """
    _, extension = os.path.splitext(filename)
    return f"{int(user_id)}_{uuid.uuid4().hex}{extension.lower()}"


def stage_file(user_id: int, file_path: str) -> str:
    """Copy a dropped file into storage and return its key.

    Reads on the node that can see the file, so the durable job that follows is
    not bound to this node. The local original is deliberately **left in place**:
    it is only removed once the jobs referencing these blobs have been committed
    (see :func:`settle`), so a publish failure leaves the user's files where they
    dropped them rather than consuming them into storage with nothing to import
    them.

    Args:
        user_id: Owner of the import.
        file_path: Absolute path of the dropped file.

    Returns:
        The storage key the bytes now live under.
    """
    with open(file_path, "rb") as handle:
        data = handle.read()

    key = build_key(user_id, os.path.basename(file_path))
    _storage().save(BULK_IMPORT_STORAGE_AREA, key, data)
    return key


def settle(staged: list[tuple[str, str]], user_id: int) -> None:
    """Remove the local originals of files whose jobs are now committed.

    Args:
        staged: ``(storage_key, file_path)`` pairs that were published.
        user_id: Owner of the import, for the log context.

    Returns:
        None.
    """
    for key, file_path in staged:
        try:
            os.remove(file_path)
        except OSError as err:
            # Not fatal: the blob is the record from here on. Logged because the
            # leftover would otherwise be re-imported on the next run.
            logger.warning(
                "Bulk import: staged a file but could not remove the local original",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, file=os.path.basename(file_path), storage_key=key),
            )


def unstage(keys: list[str]) -> None:
    """Drop staged blobs whose jobs were never published.

    Args:
        keys: Storage keys staged before the failure.

    Returns:
        None.
    """
    storage = _storage()
    for key in keys:
        try:
            storage.delete(BULK_IMPORT_STORAGE_AREA, key)
        except Exception as err:
            logger.warning(
                "Bulk import: could not drop a blob staged for a failed publish",
                exc_info=err,
                extra=core_logger.context(storage_key=key),
            )


@contextmanager
def materialized(key: str, filename: str) -> Iterator[str | None]:
    """Yield a local path for a staged blob, cleaning it up afterwards.

    Yields ``None`` when the blob is gone, which is the shape of a job whose
    file was already imported and discarded — a duplicate delivery rather than
    an error, so the caller can no-op instead of retrying forever.

    Args:
        key: The staged blob's storage key.
        filename: The dropped file's original name, preserved because the
            pipeline reads meaning from it.

    Yields:
        Path to the materialised file, or ``None`` when the blob is absent.
    """
    data = _storage().get(BULK_IMPORT_STORAGE_AREA, key)
    if data is None:
        yield None
        return

    with tempfile.TemporaryDirectory(prefix="bulk_import_") as work_dir:
        # basename() because the name travels in a durable payload a worker
        # trusts; a crafted "../.." would otherwise escape the temp directory.
        path = os.path.join(work_dir, os.path.basename(filename))
        with open(path, "wb") as handle:
            handle.write(data)
        yield path


def discard(key: str) -> None:
    """Delete a staged blob after its import succeeded.

    Args:
        key: The staged blob's storage key.

    Returns:
        None.
    """
    _storage().delete(BULK_IMPORT_STORAGE_AREA, key)


def move_to_errors(key: str, user_id: int, filename: str) -> None:
    """Move a dead-lettered blob into the import-error area.

    The trail a user follows to find out which file failed. It goes through
    storage rather than a local directory for the same reason the import does:
    the worker that dead-letters the job need not be the node holding the drop
    directory.

    Args:
        key: The staged blob's storage key.
        user_id: Owner of the import.
        filename: The dropped file's original name, recorded for the operator.

    Returns:
        None.
    """
    storage = _storage()
    try:
        data = storage.get(BULK_IMPORT_STORAGE_AREA, key)
        if data is None:
            logger.warning(
                "Bulk import: dead-lettered file is no longer staged",
                extra=core_logger.context(console=True, user_id=user_id, file=filename, storage_key=key),
            )
            return
        storage.save(BULK_IMPORT_ERROR_STORAGE_AREA, key, data)
        storage.delete(BULK_IMPORT_STORAGE_AREA, key)
        logger.error(
            "Bulk import: dead-lettered file moved to the import-error area",
            extra=core_logger.context(console=True, user_id=user_id, file=filename, storage_key=key),
        )
    except Exception as err:
        logger.error(
            "Bulk import: failed to move a dead-lettered file to the import-error area",
            exc_info=err,
            extra=core_logger.context(console=True, user_id=user_id, file=filename, storage_key=key),
        )
