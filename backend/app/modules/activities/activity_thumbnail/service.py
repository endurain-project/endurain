"""Generate, backfill, regenerate, and delete activity map thumbnails.

The behavioural core of the subsystem. Rendering (:mod:`render`) produces bytes;
this module persists/removes them through the platform ``StorageProvider`` and
records the storage *key* on the activity. It also owns the scheduled reconciling
backfill (guarded by the ``LockProvider`` so a single replica runs it) and the
    full regeneration triggered when tile settings change.
"""

from collections.abc import Iterator

from sqlalchemy.orm import Session

import core.database as core_database
import core.logger as core_logger
import infra.providers as platform_providers
import infra.runtime as platform_runtime
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.integration_service as activities_service
import modules.activities.activity_streams.integration_service as activity_streams_service
import modules.activities.activity_thumbnail.render as activity_thumbnail_render
import modules.activities.activity_thumbnail.signing as activity_thumbnail_signing
import modules.server_settings.integration_service as server_settings_integration

logger = core_logger.get_logger(__name__)

#: Rows per page for the passes that walk the whole activities table. These run
#: against every activity on the instance, so they are read in bounded batches
#: rather than materialised in one list.
_SCAN_PAGE_SIZE = 500


def _iter_activities_with_thumbnail(db: Session) -> Iterator[activities_contracts.ActivityThumbnailRef]:
    """Yield every activity carrying a thumbnail key, one bounded page at a time.

    Args:
        db: Database session.

    Yields:
        Thumbnail references, ascending by activity id.
    """
    after_id = 0
    while True:
        page = activities_service.list_activities_with_thumbnail(db, after_id=after_id, limit=_SCAN_PAGE_SIZE)
        if not page:
            return
        yield from page
        after_id = page[-1].id


def _iter_activities_without_thumbnail(db: Session) -> Iterator[list[activities_contracts.ActivityThumbnailRef]]:
    """Yield pages of activities that have no thumbnail key.

    Pages rather than rows: the caller batch-loads each page's waypoints in one
    query. The cursor always advances past the page it just read — re-reading
    from the last unrendered id would loop forever on a page whose activities
    have no GPS stream to render.

    Args:
        db: Database session.

    Yields:
        Non-empty lists of thumbnail references, ascending by activity id.
    """
    after_id = 0
    while True:
        page = activities_service.list_activities_without_thumbnail(db, after_id=after_id, limit=_SCAN_PAGE_SIZE)
        if not page:
            return
        yield page
        after_id = page[-1].id


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
        settings.tile_url or activity_thumbnail_render._DEFAULT_TILE_URL,
        settings.background_color or activity_thumbnail_render._DEFAULT_BG_COLOR,
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
    data = activity_thumbnail_render.render_activity_thumbnail(
        activity_id,
        waypoints,
        tile_url=tile_url,
        background_color=background_color,
        api_key=api_key,
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
    activities_service.set_thumbnail_key(activity_id, key, db)
    return key


def delete_activity_thumbnail(activity_id: int, storage: platform_providers.StorageProvider) -> None:
    """Delete an activity's stored thumbnail blob.

    The key is derived from the activity ID, so the (possibly already deleted)
    activity row is not needed. Idempotent: deleting a key with no blob behind it
    is a no-op for every storage backend.

    Args:
        activity_id: The activity whose thumbnail should be removed.
        storage: The blob-storage provider.

    Returns:
        None.
    """
    storage.delete(
        activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA, activity_thumbnail_signing.thumbnail_key(activity_id)
    )


def delete_and_regenerate_all_activity_thumbnails() -> None:
    """
    Delete all existing thumbnails and regenerate from scratch.

    Called when the tile server settings change and the admin has
    enabled automatic thumbnail regeneration. Deletes every stored
    thumbnail blob through the storage provider, clears the DB
    references, then triggers a full regeneration pass.

    Returns:
        None

    Raises:
        None — errors are logged; execution continues.
    """
    logger.info("Thumbnail regeneration: deleting all existing thumbnails")

    storage = platform_runtime.get_active_platform().storage

    deleted = 0
    with core_database.SessionLocal() as db:
        for activity in _iter_activities_with_thumbnail(db):
            key = activity.map_thumbnail_path
            if key is None:
                continue
            try:
                storage.delete(activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA, key)
                deleted += 1
            except Exception as err:
                logger.warning(
                    "Thumbnail regeneration: could not delete the existing thumbnail",
                    extra=core_logger.context(activity_id=activity.id, reason=str(err)),
                )
        # Clear DB references so generate_missing picks them all up.
        activities_service.clear_all_thumbnail_keys(db)

    logger.info("Thumbnail regeneration: deleted thumbnails", extra=core_logger.context(deleted=deleted))

    # Regenerate all thumbnails
    generate_missing_activity_thumbnails()


def generate_missing_activity_thumbnails() -> None:
    """
    Generate thumbnails for activities that are missing one.

    Intended to be called periodically by the scheduler. Acquires the
    coordination lock so only one replica runs the pass, then opens its
    own database session, reconciles stale references, and renders and
    stores a thumbnail for each activity whose map_thumbnail_path is NULL.

    Returns:
        None

    Raises:
        None — errors are logged per-activity; execution continues.
    """
    platform = platform_runtime.get_active_platform()
    with platform.lock.try_acquire("thumbnail_backfill") as acquired:
        if not acquired:
            logger.debug("Thumbnail scheduler: another replica holds the backfill lock; skipping")
            return
        _run_missing_thumbnail_generation(platform.storage)


def _run_missing_thumbnail_generation(storage: platform_providers.StorageProvider) -> None:
    """Reconcile stale references and render any missing thumbnails.

    Args:
        storage: The blob-storage provider.

    Returns:
        None
    """
    with core_database.SessionLocal() as db:
        # Reconcile: clear DB references whose stored blob no longer exists so
        # they are regenerated below.
        for activity in _iter_activities_with_thumbnail(db):
            key = activity.map_thumbnail_path
            if key is not None and not storage.exists(activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA, key):
                activities_service.set_thumbnail_key(activity.id, None, db)
                logger.info(
                    "Thumbnail scheduler: cleared a thumbnail path whose blob is missing",
                    extra=core_logger.context(activity_id=activity.id),
                )

        generated = 0
        candidates = 0
        tile_settings: tuple[str, str, str | None] | None = None
        for page in _iter_activities_without_thumbnail(db):
            candidates += len(page)
            # Resolved on the first page rather than up front: it reads server
            # settings and decrypts the tile API key, which is wasted work on the
            # usual pass where nothing is missing.
            if tile_settings is None:
                tile_settings = resolve_tile_settings(db)
            tile_url, background_color, api_key = tile_settings

            # Batch-load MAP-stream waypoints through the streams service (the ORM
            # stays confined to that package) as an {activity_id: waypoints} mapping.
            waypoints_by_activity_id = activity_streams_service.get_gps_waypoints_for_activities(
                [activity.id for activity in page],
                db,
            )

            for activity in page:
                waypoints = waypoints_by_activity_id.get(activity.id)

                if not waypoints:
                    continue

                key = generate_and_store_thumbnail(
                    activity.id,
                    waypoints,
                    storage,
                    db,
                    tile_url=tile_url,
                    background_color=background_color,
                    api_key=api_key,
                )

                if key is not None:
                    generated += 1

        if not candidates:
            logger.debug("Thumbnail scheduler: no activities without thumbnail found")
            return

        logger.info(
            "Thumbnail scheduler pass complete",
            extra=core_logger.context(generated=generated, candidates=candidates),
        )
