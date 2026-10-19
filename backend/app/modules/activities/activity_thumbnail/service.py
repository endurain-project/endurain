"""Generate, backfill, regenerate, and delete activity map thumbnails.

The behavioural core of the subsystem. Rendering (:mod:`render`) produces bytes;
this module persists/removes them through the platform ``StorageProvider`` and
records the storage *key* on the activity. It also owns the scheduled reconciling
backfill (guarded by the ``LockProvider`` so a single replica runs it) and the
full regeneration triggered when tile settings change.

Sessions are opened by the entry point (``integration_service``) and passed down.
"""

import functools
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Protocol

import jasil.jobs as platform_jobs
import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.integration_service as activity_streams_integration
import modules.activities.activity_thumbnail.render as activity_thumbnail_render
import modules.activities.activity_thumbnail.signing as activity_thumbnail_signing
import modules.activities.orphan_sweep as activities_orphan_sweep
import modules.server_settings.integration_service as server_settings_integration

logger = core_logger.get_logger(__name__)

#: An activity needs a start and an end point to draw a track.
_MIN_WAYPOINTS = 2

#: How long an activity that ended a backfill pass without a thumbnail waits
#: before the next pass tries it again.
THUMBNAIL_RETRY_DELAY = timedelta(hours=6)

#: Lock shared by the backfill and the full regeneration, so only one of them
#: touches the thumbnails at a time across replicas.
_BACKFILL_LOCK_NAME = "thumbnail_backfill"


class _ActivityPageFetcher(Protocol):
    """Activity scan that returns one keyset-paginated page of thumbnail references."""

    def __call__(self, db: Session, *, after_id: int, limit: int) -> list[activity_contracts.ActivityThumbnailRef]:
        """Return the page of references following ``after_id``."""
        ...


def _iter_activity_pages(
    fetch_page: _ActivityPageFetcher, db: Session
) -> Iterator[list[activity_contracts.ActivityThumbnailRef]]:
    """Yield every non-empty page returned by an activity scan.

    Args:
        db: Database session.
        fetch_page: Activity scan operation to page through.

    Yields:
        Non-empty pages of activity thumbnail references, ordered by id.

    Returns:
        Non-empty pages of thumbnail references, ordered by id.
    """
    after_id = 0
    while True:
        page = fetch_page(
            db,
            after_id=after_id,
            limit=core_pagination.DEFAULT_MAINTENANCE_BATCH_SIZE,
        )
        if not page:
            return
        yield page
        after_id = page[-1].id


def _iter_activities_with_thumbnail(db: Session) -> Iterator[activity_contracts.ActivityThumbnailRef]:
    """Yield every activity carrying a thumbnail key, one bounded page at a time.

    Args:
        db: Database session.

    Yields:
        Thumbnail references, ascending by activity id.

    Returns:
        Thumbnail references, in id order.
    """
    for page in _iter_activity_pages(activity_integration.list_activities_with_thumbnail, db):
        yield from page


def _iter_activities_without_thumbnail(
    due_at: datetime, db: Session
) -> Iterator[list[activity_contracts.ActivityThumbnailRef]]:
    """Yield pages of activities that have no thumbnail key and are due an attempt.

    Pages rather than rows: the caller batch-loads each page's waypoints in one
    query. The cursor always advances past the page it just read — re-reading
    from the last unrendered id would loop forever on a page whose activities
    have no GPS stream to render.

    Args:
        due_at: Activities deferred past this instant are skipped.
        db: Database session.

    Yields:
        Non-empty lists of thumbnail references, ascending by activity id.

    Returns:
        Pages of thumbnail references, in id order.
    """
    yield from _iter_activity_pages(
        functools.partial(activity_integration.list_activities_without_thumbnail, due_at=due_at), db
    )


def resolve_tile_settings(db: Session) -> tuple[str, str, str | None]:
    """Resolve tile URL, background color, and (decrypted) API key.

    Args:
        db: Database session used to read server settings.

    Returns:
        A ``(tile_url, background_color, api_key)`` tuple, using built-in
        defaults when server settings are unavailable.
    """
    settings = server_settings_integration.get_tile_server_settings(db)
    return (
        settings.tile_url or activity_thumbnail_render.DEFAULT_TILE_URL,
        settings.background_color or activity_thumbnail_render.DEFAULT_BG_COLOR,
        settings.api_key,
    )


def generate_and_store_thumbnail(
    activity_id: int,
    waypoints: list[dict],
    storage: platform_providers.StorageProvider,
    db: Session,
    *,
    tile_url: str,
    background_color: str,
    api_key: str | None,
) -> str | None:
    """Render, persist, and record an activity thumbnail.

    Renders the map to WebP bytes, saves them through the storage provider under
    the activity's key, and stores that key on the activity row.

    Args:
        activity_id: Target activity ID.
        waypoints: GPS ``{"lat", "lon"}`` waypoints for the route.
        storage: The blob-storage provider.
        db: Database session used to persist the key.
        tile_url: Tile URL template.
        background_color: Map canvas background color.
        api_key: Optional tile-provider API key.

    Returns:
        The stored storage key, or ``None`` when rendering was skipped/failed.
    """
    # End the read transaction before the tile fetches: it would otherwise pin a
    # pool connection and a snapshot for as long as the tile server takes.
    db.commit()
    data = activity_thumbnail_render.render_activity_thumbnail(
        activity_id,
        waypoints,
        tile_url=tile_url,
        background_color=background_color,
        api_key=api_key,
        user_agent=f"Endurain {core_config.API_VERSION} - StaticMap backend thumbnail generator",
    )
    if data is None:
        return None
    key = activity_thumbnail_signing.thumbnail_key(activity_id)
    storage.save(
        activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA,
        key,
        data,
        activity_thumbnail_render.THUMBNAIL_CONTENT_TYPE,
    )
    if not activity_integration.set_thumbnail_key(activity_id, key, db):
        # The activity was deleted while the tiles rendered, and its cleanup event
        # may already have run, so nothing else names this blob.
        storage.delete(activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA, key)
        return None
    db.commit()
    logger.info("Thumbnail stored", extra=core_logger.context(activity_id=activity_id))
    return key


def generate_thumbnail_for_activity(
    activity_id: int,
    user_id: int,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> str | None:
    """Read an activity's GPS track and render and store its thumbnail.

    A no-op for an activity without at least two GPS waypoints, so non-GPS
    activities cost nothing.

    Args:
        activity_id: The activity to generate a thumbnail for.
        user_id: The owning user, recorded when the generation is skipped.
        storage: The blob-storage provider.
        db: Database session.

    Returns:
        The stored storage key, or ``None`` when the activity has too few
        waypoints or rendering was skipped/failed.
    """
    waypoints = activity_streams_integration.get_stream_for_derivation(
        activity_id, activity_streams_constants.STREAM_TYPE_MAP, db
    )
    if waypoints is None or len(waypoints.stream_waypoints) < _MIN_WAYPOINTS:
        # Logged because "my activity has no thumbnail" is otherwise
        # indistinguishable from a failure.
        logger.debug(
            "Skipping thumbnail generation: too few GPS waypoints",
            extra=core_logger.context(
                activity_id=activity_id,
                user_id=user_id,
                waypoint_count=0 if waypoints is None else len(waypoints.stream_waypoints),
                minimum_waypoints=_MIN_WAYPOINTS,
            ),
        )
        return None
    tile_url, background_color, api_key = resolve_tile_settings(db)
    return generate_and_store_thumbnail(
        activity_id,
        waypoints.stream_waypoints,
        storage,
        db,
        tile_url=tile_url,
        background_color=background_color,
        api_key=api_key,
    )


def read_activity_thumbnail(activity_id: int, token: str, storage: platform_providers.StorageProvider) -> bytes:
    """Return an activity's thumbnail bytes when the signed token is valid.

    Args:
        activity_id: The activity whose thumbnail to read.
        token: The signed access token minted at serialization time.
        storage: The blob-storage provider.

    Returns:
        The stored WebP thumbnail bytes.

    Raises:
        NotFoundError: When the token is invalid/forged or no thumbnail exists
            (404 rather than 403 avoids confirming the resource to an
            unauthorized caller).
    """
    if not activity_thumbnail_signing.verify_thumbnail_token(activity_id, token):
        # Security-relevant: either a forged token or one replayed against a
        # different activity. Logged at warning so a probing pattern is visible.
        logger.warning(
            "Rejected a thumbnail request with an invalid signed token",
            extra=core_logger.context(activity_id=activity_id),
        )
        raise core_exceptions.AccessConcealedError("Thumbnail not found")

    data = storage.get(
        activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA,
        activity_thumbnail_signing.thumbnail_key(activity_id),
    )
    if data is None:
        raise core_exceptions.NotFoundError("Thumbnail not found")
    return data


def delete_activity_thumbnail(activity_id: int, storage: platform_providers.StorageProvider) -> None:
    """Delete an activity's stored thumbnail blob.

    The key is derived from the activity ID, so the (possibly already deleted)
    activity row is not needed. Idempotent: deleting a key with no blob behind it
    is a no-op for every storage backend.

    Args:
        activity_id: The activity whose thumbnail should be removed.
        storage: The blob-storage provider.
    """
    storage.delete(
        activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA, activity_thumbnail_signing.thumbnail_key(activity_id)
    )


def delete_and_regenerate_all_activity_thumbnails(
    storage: platform_providers.StorageProvider,
    lock: platform_providers.LockProvider,
    clock: platform_providers.ClockProvider,
    db: Session,
) -> None:
    """Delete all existing thumbnails and regenerate from scratch.

    Called when the tile server settings change and the admin has
    enabled automatic thumbnail regeneration. Deletes every stored
    thumbnail blob through the storage provider, clears the DB
    references, then triggers a full regeneration pass. A failure on one
    activity is logged and the pass continues.

    Args:
        storage: The blob-storage provider.
        lock: The coordination lock provider.
        clock: The platform clock.
        db: Database session.

    Raises:
        ConflictError: When another replica holds the backfill lock.
    """
    with lock.try_acquire(_BACKFILL_LOCK_NAME) as acquired:
        if not acquired:
            # Dropping the request would leave the old tiles in every thumbnail,
            # so the caller is told; a durable job retries with backoff.
            logger.warning("Thumbnail regeneration: another replica holds the backfill lock")
            raise core_exceptions.ConflictError("Thumbnail generation is already running")
        if not _delete_all_thumbnails(storage, db):
            return
        _run_missing_thumbnail_generation(storage, clock.now(), db)


def _delete_all_thumbnails(storage: platform_providers.StorageProvider, db: Session) -> bool:
    """Delete every stored thumbnail blob, then clear the keys that named them.

    Args:
        storage: The blob-storage provider.
        db: Database session.

    Returns:
        ``False`` when the durable job lost its lease part-way, so the caller must
        not carry on: the keys are left set and the next pass reconciles them.
    """
    logger.info("Thumbnail regeneration: deleting all existing thumbnails")

    deleted = 0
    for activity in _iter_activities_with_thumbnail(db):
        if platform_jobs.lease_lost():
            logger.warning("Thumbnail regeneration: lease lost; stopping before the keys are cleared")
            return False
        key = activity.map_thumbnail_path
        if key is None:
            continue
        try:
            storage.delete(activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA, key)
            deleted += 1
        except Exception as err:
            logger.warning(
                "Thumbnail regeneration: could not delete the existing thumbnail",
                exc_info=err,
                extra=core_logger.context(activity_id=activity.id),
            )
    # Clear DB references so the generation pass picks them all up.
    activity_integration.clear_all_thumbnail_keys(db)
    db.commit()

    logger.info("Thumbnail regeneration: deleted thumbnails", extra=core_logger.context(deleted=deleted))
    return True


def generate_missing_activity_thumbnails(
    storage: platform_providers.StorageProvider,
    lock: platform_providers.LockProvider,
    clock: platform_providers.ClockProvider,
    db: Session,
) -> None:
    """Generate thumbnails for activities that are missing one.

    Intended to be called periodically by the scheduler. Acquires the
    coordination lock so only one replica runs the pass, then reconciles
    stale references and renders and stores a thumbnail for each activity
    whose map_thumbnail_path is NULL. A failure on one activity is logged and
    the pass continues.

    Args:
        storage: The blob-storage provider.
        lock: The coordination lock provider.
        clock: The platform clock, for the due time and the retry time.
        db: Database session.
    """
    with lock.try_acquire(_BACKFILL_LOCK_NAME) as acquired:
        if not acquired:
            logger.debug("Thumbnail scheduler: another replica holds the backfill lock; skipping")
            return
        _run_missing_thumbnail_generation(storage, clock.now(), db)


def _clear_references_to_missing_blobs(storage: platform_providers.StorageProvider, db: Session) -> None:
    """Clear thumbnail keys whose stored blob no longer exists.

    One listing of the area answers for every activity, instead of an existence
    check per activity per pass (a HEAD request each on object storage). Only the
    activity ids are kept, one integer per stored thumbnail, rather than the keys. A key
    missing from the listing is confirmed individually before it is cleared: the
    listing was taken before the page was read, so a blob a subscriber stored in
    between would otherwise look missing.

    Args:
        storage: The blob-storage provider.
        db: Database session.
    """
    existing = {
        activity_id
        for key, _modified in storage.iter_objects(activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA)
        if (activity_id := _activity_id_of_thumbnail_key(key)) is not None
    }
    for activity in _iter_activities_with_thumbnail(db):
        key = activity.map_thumbnail_path
        if key is None or activity.id in existing:
            continue
        if storage.exists(activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA, key):
            continue
        # Conditional on the key still being the one read: a subscriber may have stored a
        # fresh thumbnail since, and that one must survive.
        if activity_integration.set_thumbnail_key(activity.id, None, db, expected_key=key):
            logger.info(
                "Thumbnail scheduler: cleared a thumbnail path whose blob is missing",
                extra=core_logger.context(activity_id=activity.id),
            )
            db.commit()


def _run_missing_thumbnail_generation(storage: platform_providers.StorageProvider, now: datetime, db: Session) -> None:
    """Reconcile stale references and render any missing thumbnails.

    An activity that ends the pass without a thumbnail (no GPS, a skipped or
    failed render) is deferred by :data:`THUMBNAIL_RETRY_DELAY`, so the passes
    in between neither re-read it nor repeat a tile-server round trip for it.

    Args:
        storage: The blob-storage provider.
        now: The current time; activities deferred past it are skipped.
        db: Database session.
    """
    _clear_references_to_missing_blobs(storage, db)

    retry_at = now + THUMBNAIL_RETRY_DELAY
    generated = 0
    candidates = 0
    tile_settings: tuple[str, str, str | None] | None = None
    for page in _iter_activities_without_thumbnail(now, db):
        candidates += len(page)
        # Resolved on the first page rather than up front: it reads server
        # settings and decrypts the tile API key, which is wasted work on the
        # usual pass where nothing is missing.
        if tile_settings is None:
            tile_settings = resolve_tile_settings(db)
        tile_url, background_color, api_key = tile_settings

        # Batch-load MAP-stream waypoints through the streams service (the ORM
        # stays confined to that package) as an {activity_id: waypoints} mapping.
        waypoints_by_activity_id = activity_streams_integration.get_gps_waypoints_for_activities(
            [activity.id for activity in page],
            db,
        )

        unrendered: list[int] = []
        for activity in page:
            if platform_jobs.lease_lost():
                logger.warning("Thumbnail scheduler: lease lost; stopping the pass")
                return
            waypoints = waypoints_by_activity_id.get(activity.id)

            if not waypoints:
                unrendered.append(activity.id)
                continue

            try:
                key = generate_and_store_thumbnail(
                    activity.id,
                    waypoints,
                    storage,
                    db,
                    tile_url=tile_url,
                    background_color=background_color,
                    api_key=api_key,
                )
            except Exception as err:
                # One bad activity must not stop the rest of the pass.
                db.rollback()
                logger.warning(
                    "Thumbnail scheduler: could not generate a thumbnail",
                    exc_info=err,
                    extra=core_logger.context(activity_id=activity.id),
                )
                key = None

            if key is None:
                unrendered.append(activity.id)
            else:
                generated += 1

        if unrendered:
            activity_integration.defer_thumbnail_attempts(unrendered, retry_at, db)
            db.commit()

    if not candidates:
        logger.debug("Thumbnail scheduler: no activities without thumbnail found")
        return

    logger.info(
        "Thumbnail scheduler pass complete",
        extra=core_logger.context(generated=generated, candidates=candidates),
    )


def _activity_id_of_thumbnail_key(key: str) -> int | None:
    """Return the activity id a ``{id}.webp`` thumbnail key names.

    Args:
        key: A storage key in the thumbnail area.

    Returns:
        The activity id, or ``None`` when the key is not a thumbnail key.
    """
    stem, suffix = key.rsplit(".", 1) if "." in key else (key, "")
    return int(stem) if suffix == "webp" and stem.isdecimal() else None


def sweep_orphaned_thumbnails(storage: platform_providers.StorageProvider, db: Session) -> int:
    """Delete thumbnail blobs whose activity no longer exists.

    The storage-side net for the cleanup subscriber: a dropped
    ``activity.deleted`` event leaves a blob no row names, so only a scan of the
    area can find it.

    Args:
        storage: The blob-storage provider.
        db: Database session.

    Returns:
        The number of blobs deleted.
    """
    return activities_orphan_sweep.sweep_orphaned_blobs(
        storage,
        activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA,
        lambda ids: activity_integration.filter_existing_activity_ids(ids, db),
        _activity_id_of_thumbnail_key,
    )
