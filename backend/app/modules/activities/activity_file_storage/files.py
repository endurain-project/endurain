"""Storage addressing and removal for retained activity source files.

Package-private: the key layout is shared by the service and the cleanup subscriber, neither of which may import
the other's private names. A file with a row is stored under ``files/{file_id}{ext}`` and the row holds the key.
A file stored before rows existed has no row: its key is derived from the activity id plus one of the known source
extensions, and is probed and deleted through the legacy functions below until those files are adopted.
"""

import uuid

import jasil.providers as platform_providers

import modules.activities.activity_file_storage.constants as activity_file_storage_constants

# The ``processed`` hierarchy belongs in the key because JASIL storage areas are
# single namespace components.
_PROCESSED_KEY_PREFIX = "processed"

# The activity source-file extensions we retain. A ``.gz`` upload is decompressed before storage, so only the inner
# formats are ever stored.
STORED_EXTENSIONS = (".gpx", ".fit", ".tcx")


def normalize_extension(extension: str) -> str:
    """Return an extension lowercased with its leading dot.

    Args:
        extension: The extension, with or without its dot (``".FIT"`` or ``"fit"``).

    Returns:
        The extension, e.g. ``".fit"``.
    """
    return extension.lower() if extension.startswith(".") else f".{extension.lower()}"


def file_key(file_id: uuid.UUID, extension: str) -> str:
    """Return the storage key of a retained file that has a row.

    Args:
        file_id: The file row's id.
        extension: The source-file extension, with or without a leading dot.

    Returns:
        The storage key, e.g. ``"files/{file_id}.fit"``.
    """
    return f"{activity_file_storage_constants.FILE_KEY_PREFIX}/{file_id}{normalize_extension(extension)}"


def legacy_file_key(activity_id: uuid.UUID, extension: str) -> str:
    """Return the storage key of a file stored before rows existed.

    Args:
        activity_id: The owning activity id.
        extension: The source-file extension, with or without a leading dot.

    Returns:
        The storage key, e.g. ``"processed/{activity_id}.fit"``.
    """
    return f"{_PROCESSED_KEY_PREFIX}/{activity_id}{normalize_extension(extension)}"


def delete_legacy_files(
    activity_id: uuid.UUID,
    storage: platform_providers.StorageProvider,
) -> None:
    """Delete the file an activity without a row has stored, whichever extension it has.

    Deletes are idempotent (a missing blob is a no-op on every backend), so this is safe to call for an activity
    that never had a retained file.

    Args:
        activity_id: The owning activity id.
        storage: The blob-storage provider.
    """
    for extension in STORED_EXTENSIONS:
        storage.delete(
            activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA, legacy_file_key(activity_id, extension)
        )


def read_legacy_file(
    activity_id: uuid.UUID,
    storage: platform_providers.StorageProvider,
) -> tuple[str, bytes] | None:
    """Read the file an activity without a row has stored, probing the known extensions.

    Args:
        activity_id: The owning activity id.
        storage: The blob-storage provider.

    Returns:
        The ``(extension, data)`` of the first extension found, or ``None`` when there is none.
    """
    for extension in STORED_EXTENSIONS:
        data = storage.get(
            activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA, legacy_file_key(activity_id, extension)
        )
        if data is not None:
            return extension, data
    return None


def activity_id_of_processed_key(key: str) -> uuid.UUID | None:
    """Return the activity id a ``processed/{id}.{ext}`` key names.

    Only the canonical lowercase UUID layout is recognised; any other key yields ``None``.

    Args:
        key: A storage key in the activity-files area.

    Returns:
        The activity id, or ``None`` for any other key (staged uploads and ``files/`` keys share the area and must
        not be treated as legacy files).
    """
    stem, dot, extension = key.removeprefix(f"{_PROCESSED_KEY_PREFIX}/").rpartition(".")
    owned = key.startswith(f"{_PROCESSED_KEY_PREFIX}/") and f".{extension}" in STORED_EXTENSIONS
    if not (owned and dot):
        return None
    try:
        activity_id = uuid.UUID(stem)
    except ValueError:
        return None
    return activity_id if stem == str(activity_id) else None
