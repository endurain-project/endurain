"""Storage addressing and removal for retained activity source files.

Package-private: the key layout and the delete are shared by the published
surface (``integration_service``) and the cleanup subscriber, neither of which
may import the other's private names. The database stores no key for these
files: it is derived from the activity id plus one of the known source
extensions.
"""

import jasil.providers as platform_providers

import modules.activities.activity_file_storage.constants as activity_file_storage_constants

# The ``processed`` hierarchy belongs in the key because JASIL storage areas are
# single namespace components.
_PROCESSED_KEY_PREFIX = "processed"

# The activity source-file extensions we retain and can address by activity id.
# A ``.gz`` upload is decompressed before storage, so only the inner formats are
# ever stored under an ``{id}`` key.
STORED_EXTENSIONS = (".gpx", ".fit", ".tcx")


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


def processed_storage_key(key: str) -> str:
    """Return the storage key placed under the ``processed`` hierarchy.

    Args:
        key: The activity file key, e.g. ``"42.fit"``.

    Returns:
        The prefixed storage key, e.g. ``"processed/42.fit"``.
    """
    return f"{_PROCESSED_KEY_PREFIX}/{key}"


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
    """
    for extension in STORED_EXTENSIONS:
        key = activity_file_key(activity_id, extension)
        storage.delete(activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA, processed_storage_key(key))


def activity_id_of_processed_key(key: str) -> int | None:
    """Return the activity id a ``processed/{id}.{ext}`` key names.

    Args:
        key: A storage key in the activity-files area.

    Returns:
        The activity id, or ``None`` for any other key (staged uploads share the
        area and must not be treated as retained files).
    """
    stem, dot, extension = key.removeprefix(f"{_PROCESSED_KEY_PREFIX}/").rpartition(".")
    owned = key.startswith(f"{_PROCESSED_KEY_PREFIX}/") and f".{extension}" in STORED_EXTENSIONS
    return int(stem) if owned and dot and stem.isdecimal() else None
