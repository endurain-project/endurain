"""Persist, read, and delete the retained activity source file via ``StorageProvider``.

The behavioural core of the subsystem. Ingestion hands over the parsed file's
bytes; this module stores/reads/removes them through the platform
``StorageProvider`` under a domain-owned *area*, keyed by activity id. It mirrors
the thumbnail subsystem's use of the provider, so the retained file lives on
local disk or object storage identically and file-based ingestion is no longer
tied to the API node's filesystem.

The database stores no key for these files: the key is derived from the activity
id plus one of the known source extensions, so reads/deletes probe those
extensions rather than reading a column. There is no servable URL — the retained
file is only consumed in-process (profile export) and on cleanup, never served.
"""

import core.logger as core_logger
import infra.providers as platform_providers

logger = core_logger.get_logger(__name__)

# Domain-owned storage namespace for retained activity source files. For the
# ``local`` backend this maps to ``{DATA_DIR}/activity_files/processed`` — the
# exact directory the files were previously moved to — so existing self-host
# installs need no data migration; for S3 it is the object key prefix.
ACTIVITY_FILE_STORAGE_AREA = "activity_files/processed"

# The activity source-file extensions we retain and can address by activity id.
# A ``.gz`` upload is decompressed before storage, so only the inner formats are
# ever stored under an ``{id}`` key.
_STORED_EXTENSIONS = (".gpx", ".fit", ".tcx")


def activity_file_key(activity_id: int, extension: str) -> str:
    """Return the storage key for an activity's retained source file.

    Args:
        activity_id: The owning activity id.
        extension: The source-file extension, with or without a leading dot
            (e.g. ``".fit"`` or ``"fit"``).

    Returns:
        The storage key, e.g. ``"42.fit"``.
    """
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"{activity_id}{ext.lower()}"


def store_activity_file(
    activity_id: int,
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> str:
    """Persist one activity's source file and return its storage key.

    Args:
        activity_id: The owning activity id.
        extension: The source-file extension (e.g. ``".fit"``).
        data: The raw (already-decompressed) file bytes.
        storage: The blob-storage provider.

    Returns:
        The storage key the file was saved under.
    """
    key = activity_file_key(activity_id, extension)
    storage.save(ACTIVITY_FILE_STORAGE_AREA, key, data)
    logger.debug(
        "Stored the activity source file",
        extra=core_logger.context(activity_id=activity_id, storage_key=key),
    )
    return key


def store_activity_file_for_ids(
    activity_ids: list[int],
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> None:
    """Persist the same source file under each of several activities' keys.

    A single upload can yield more than one activity (a multi-activity ``.fit``),
    and each activity owns its own retained copy so its lifecycle (export,
    deletion) is independent. The bytes are written once per id.

    Args:
        activity_ids: The activity ids to store the file under.
        extension: The source-file extension (e.g. ``".fit"``).
        data: The raw (already-decompressed) file bytes.
        storage: The blob-storage provider.

    Returns:
        None.
    """
    for activity_id in activity_ids:
        store_activity_file(activity_id, extension, data, storage)


def get_activity_file(
    activity_id: int,
    storage: platform_providers.StorageProvider,
) -> tuple[str, bytes] | None:
    """Read an activity's retained source file, probing the known extensions.

    Args:
        activity_id: The owning activity id.
        storage: The blob-storage provider.

    Returns:
        A ``(key, data)`` tuple for the first stored extension found, or ``None``
        when the activity has no retained source file.
    """
    for extension in _STORED_EXTENSIONS:
        key = activity_file_key(activity_id, extension)
        data = storage.get(ACTIVITY_FILE_STORAGE_AREA, key)
        if data is not None:
            return key, data
    return None


def delete_activity_file(
    activity_id: int,
    storage: platform_providers.StorageProvider,
) -> None:
    """Delete an activity's retained source file(s).

    Deletes every known-extension key for the activity. Deletes are idempotent
    (a missing blob is a no-op on every backend), so this is safe to call for an
    activity that never had a retained file.

    Args:
        activity_id: The owning activity id.
        storage: The blob-storage provider.

    Returns:
        None.
    """
    for extension in _STORED_EXTENSIONS:
        storage.delete(ACTIVITY_FILE_STORAGE_AREA, activity_file_key(activity_id, extension))
