"""Storage-side sweep for blobs whose activity no longer exists.

Cleanup subscribers derive a blob's key from the deleted activity's id, but a
dropped ``activity.deleted`` event leaves nothing that names the blob: no row
remains to backfill from. This walks the storage area instead and deletes keys
whose owning activity is gone.

A second sweep covers blobs whose own row is gone while the activity lives on
(a failed best-effort delete after the row was removed).

Dependency-free on purpose: the caller supplies the key parser and the
existence lookup, so the helper imports no module.
"""

from collections.abc import Callable, Iterator
from itertools import batched
from time import time

import jasil.providers as platform_providers

#: A blob younger than this is never swept, so a blob written moments before its
#: row commits is not mistaken for an orphan.
MIN_AGE_SECONDS = 3600

_BATCH_SIZE = 500


def sweep_orphaned_blobs(
    storage: platform_providers.StorageProvider,
    area: str,
    existing_ids: Callable[[list[int]], set[int]],
    activity_id_of: Callable[[str], int | None],
    *,
    prefix: str = "",
    min_age_seconds: int = MIN_AGE_SECONDS,
) -> int:
    """Delete blobs in ``area`` whose activity row no longer exists.

    Args:
        storage: The blob-storage provider.
        area: The storage area to scan.
        existing_ids: Returns which of the given activity ids still exist.
        activity_id_of: Maps a storage key to its activity id, or ``None`` for a
            key this sweep does not own (left untouched).
        prefix: Restricts the scan to one key root inside the area.
        min_age_seconds: Skip blobs modified more recently than this.

    Returns:
        The number of blobs deleted.
    """
    cutoff = time() - min_age_seconds
    return sum(
        _delete_orphans(storage, area, batch, existing_ids)
        for batch in batched(_candidates(storage, area, prefix, activity_id_of, cutoff), _BATCH_SIZE, strict=False)
    )


def _candidates(
    storage: platform_providers.StorageProvider,
    area: str,
    prefix: str,
    activity_id_of: Callable[[str], int | None],
    cutoff: float,
) -> Iterator[tuple[str, int]]:
    """Yield ``(key, activity id)`` for old-enough blobs this sweep owns.

    Args:
        storage: The blob-storage provider.
        area: The storage area to scan.
        prefix: Key root to scan.
        activity_id_of: Maps a key to its activity id, or ``None``.
        cutoff: Epoch seconds; newer blobs are skipped.

    Returns:
        An iterator of ``(key, activity id)``.
    """
    for key, modified in storage.iter_objects(area, prefix):
        activity_id = activity_id_of(key)
        if activity_id is not None and modified <= cutoff:
            yield key, activity_id


def _delete_orphans(
    storage: platform_providers.StorageProvider,
    area: str,
    batch: tuple[tuple[str, int], ...],
    existing_ids: Callable[[list[int]], set[int]],
) -> int:
    """Delete the blobs of one batch whose activity is gone.

    Args:
        storage: The blob-storage provider.
        area: The storage area the keys live in.
        batch: ``(key, activity id)`` pairs.
        existing_ids: Returns which of the given activity ids still exist.

    Returns:
        The number of blobs deleted.
    """
    alive = existing_ids(sorted({activity_id for _key, activity_id in batch}))
    orphans = [key for key, activity_id in batch if activity_id not in alive]
    for key in orphans:
        storage.delete(area, key)
    return len(orphans)


def sweep_unreferenced_blobs(
    storage: platform_providers.StorageProvider,
    area: str,
    referenced_keys: Callable[[list[str]], set[str]],
    *,
    min_age_seconds: int = MIN_AGE_SECONDS,
) -> int:
    """Delete blobs in ``area`` that no row names.

    Args:
        storage: The blob-storage provider.
        area: The storage area to scan.
        referenced_keys: Returns which of the given keys a row still names.
        min_age_seconds: Skip blobs modified more recently than this.

    Returns:
        The number of blobs deleted.
    """
    cutoff = time() - min_age_seconds
    old_keys = (key for key, modified in storage.iter_objects(area, "") if modified <= cutoff)
    removed = 0
    for batch in batched(old_keys, _BATCH_SIZE, strict=False):
        named = referenced_keys(list(batch))
        for key in batch:
            if key not in named:
                storage.delete(area, key)
                removed += 1
    return removed
