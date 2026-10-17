"""Public storage operations for retained activity source files.

The behavioural core of the subsystem. Ingestion hands over the parsed file's
bytes; this module stores/reads/removes them through the platform
``StorageProvider`` under a domain-owned *area*, keyed by activity id. It mirrors
the thumbnail subsystem's use of the provider, so the retained file lives on
local disk or object storage identically and file-based ingestion is not tied to
the API node's filesystem.

The database stores no key for these files: the key is derived from the activity
id plus one of the known source extensions, so reads/deletes probe those
extensions rather than reading a column. There is no servable URL — the retained
file is only consumed in-process (profile export) and on cleanup, never served.
"""

import jasil.providers as platform_providers

import core.logger as core_logger
import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.files as activity_file_storage_files

logger = core_logger.get_logger(__name__)


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
    key = activity_file_storage_files.activity_file_key(activity_id, extension)
    storage.save(
        activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA,
        activity_file_storage_files.processed_storage_key(key),
        data,
    )
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
    for extension in activity_file_storage_files.STORED_EXTENSIONS:
        key = activity_file_storage_files.activity_file_key(activity_id, extension)
        data = storage.get(
            activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA,
            activity_file_storage_files.processed_storage_key(key),
        )
        if data is not None:
            return key, data
    return None
