"""Storage-side sweeps for blobs that no row owns or names any more.

A cleanup subscriber or a best-effort delete can miss a blob: a dropped event, or a storage failure
after the row changed, leaves nothing that names it. These walk a storage area instead and delete
what is left, as the reconciliation net of the area's owner.

The first sweep deletes keys whose owning row is gone; the second deletes keys no row names.

The helpers import no module: the caller supplies the key parser and the lookup. Each opens one
short session per batch for that lookup and closes it before any storage call, so no connection
waits on an object-storage round trip.
"""

from collections.abc import Callable, Iterator
from itertools import batched
from time import time

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.database as core_database

#: A blob younger than this is never swept, so a blob written moments before its
#: row commits is not mistaken for an orphan.
MIN_AGE_SECONDS = 3600

_BATCH_SIZE = 500


def sweep_orphaned_blobs(
    storage: platform_providers.StorageProvider,
    area: str,
    existing_ids: Callable[[list[int], Session], set[int]],
    owner_id_of: Callable[[str], int | None],
    *,
    prefix: str = "",
    min_age_seconds: int = MIN_AGE_SECONDS,
) -> int:
    """Delete blobs in ``area`` whose owning row no longer exists.

    Args:
        storage: The blob-storage provider.
        area: The storage area to scan.
        existing_ids: Returns which of the given owner ids still exist, given a session.
        owner_id_of: Maps a storage key to its owner's id, or ``None`` for a
            key this sweep does not own (left untouched).
        prefix: Restricts the scan to one key root inside the area.
        min_age_seconds: Skip blobs modified more recently than this.

    Returns:
        The number of blobs deleted.
    """
    cutoff = time() - min_age_seconds
    return sum(
        _delete_orphans(storage, area, batch, existing_ids)
        for batch in batched(_candidates(storage, area, prefix, owner_id_of, cutoff), _BATCH_SIZE, strict=False)
    )


def _candidates(
    storage: platform_providers.StorageProvider,
    area: str,
    prefix: str,
    owner_id_of: Callable[[str], int | None],
    cutoff: float,
) -> Iterator[tuple[str, int]]:
    """Yield ``(key, owner id)`` for old-enough blobs this sweep owns.

    Args:
        storage: The blob-storage provider.
        area: The storage area to scan.
        prefix: Key root to scan.
        owner_id_of: Maps a key to its owner's id, or ``None``.
        cutoff: Epoch seconds; newer blobs are skipped.

    Returns:
        An iterator of ``(key, owner id)``.
    """
    for key, modified in storage.iter_objects(area, prefix):
        owner_id = owner_id_of(key)
        if owner_id is not None and modified <= cutoff:
            yield key, owner_id


def _delete_orphans(
    storage: platform_providers.StorageProvider,
    area: str,
    batch: tuple[tuple[str, int], ...],
    existing_ids: Callable[[list[int], Session], set[int]],
) -> int:
    """Delete the blobs of one batch whose owner is gone.

    Args:
        storage: The blob-storage provider.
        area: The storage area the keys live in.
        batch: ``(key, owner id)`` pairs.
        existing_ids: Returns which of the given owner ids still exist, given a session.

    Returns:
        The number of blobs deleted.
    """
    with core_database.SessionLocal() as db:
        alive = existing_ids(sorted({owner_id for _key, owner_id in batch}), db)
    orphans = [key for key, owner_id in batch if owner_id not in alive]
    for key in orphans:
        storage.delete(area, key)
    return len(orphans)


def sweep_unreferenced_blobs(
    storage: platform_providers.StorageProvider,
    area: str,
    referenced_keys: Callable[[list[str], Session], set[str]],
    *,
    min_age_seconds: int = MIN_AGE_SECONDS,
) -> int:
    """Delete blobs in ``area`` that no row names.

    Args:
        storage: The blob-storage provider.
        area: The storage area to scan.
        referenced_keys: Returns which of the given keys a row still names, given a session.
        min_age_seconds: Skip blobs modified more recently than this.

    Returns:
        The number of blobs deleted.
    """
    cutoff = time() - min_age_seconds
    old_keys = (key for key, modified in storage.iter_objects(area, "") if modified <= cutoff)
    removed = 0
    for batch in batched(old_keys, _BATCH_SIZE, strict=False):
        with core_database.SessionLocal() as db:
            named = referenced_keys(list(batch), db)
        for key in batch:
            if key not in named:
                storage.delete(area, key)
                removed += 1
    return removed
