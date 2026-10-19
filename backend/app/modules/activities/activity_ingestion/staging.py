"""Helpers for moving staged blobs between storage and a local working file.

The parsers work on file paths, so a worker that holds a blob key materialises the
bytes to a temporary file first. The copy streams, so a large archive or activity
file is never held in memory, and the key — not a path on some node — is what travels
between processes, which is what lets any worker in the fleet run the job.
"""

import shutil

import jasil.providers as platform_providers


def copy_blob_to_path(area: str, key: str, path: str, storage: platform_providers.StorageProvider) -> bool:
    """Copy a stored blob to a local file without holding it in memory.

    Args:
        area: The storage area the blob lives in.
        key: The blob's storage key.
        path: Destination file; created or overwritten.
        storage: The blob-storage provider.

    Returns:
        ``True`` when copied, ``False`` when the blob does not exist.
    """
    try:
        source = storage.open_stream(area, key)
    except FileNotFoundError:
        return False
    with source, open(path, "wb") as destination:
        shutil.copyfileobj(source, destination)
    return True
