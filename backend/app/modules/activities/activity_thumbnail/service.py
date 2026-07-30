"""Generate, backfill, regenerate, and delete activity map thumbnails.

The behavioural core of the subsystem. Rendering (:mod:`render`) produces bytes;
this module persists/removes them through the platform ``StorageProvider`` and
records the storage *key* on the activity. It also owns the scheduled reconciling
backfill (guarded by the ``LockProvider`` so a single replica runs it) and the
    full regeneration triggered when tile settings change.
"""

from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.database as core_database
import core.logger as core_logger
import infra.providers as platform_providers
import infra.runtime as platform_runtime
import modules.activities.activity.crud as activities_crud
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_thumbnail.render as activity_thumbnail_render
import modules.activities.activity_thumbnail.signing as activity_thumbnail_signing
import modules.server_settings.crud as server_settings_crud

logger = core_logger.get_logger(__name__)


def resolve_tile_settings(db: Session) -> tuple[str, str, str | None]:
    """Resolve tile URL, background color, and (decrypted) API key.

    Args:
        db: Database session used to read server settings.

    Returns:
        A ``(tile_url, background_color, api_key)`` tuple, using built-in
        defaults when server settings are unavailable.
    """
    server_settings = server_settings_crud.get_server_settings(db)
    tile_url = server_settings.tileserver_url if server_settings else activity_thumbnail_render._DEFAULT_TILE_URL
    background_color = (
        server_settings.map_background_color if server_settings else activity_thumbnail_render._DEFAULT_BG_COLOR
    )
    api_key = None
    if server_settings and server_settings.tileserver_api_key:
        api_key = core_cryptography.decrypt_token_fernet(server_settings.tileserver_api_key)
    return tile_url, background_color, api_key


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
    activities_crud.set_activity_thumbnail_path(activity_id, key, db)
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
        for activity in activities_crud.get_activities_with_thumbnail(db):
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
        activities_crud.clear_all_activity_thumbnail_paths(db)

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
        for activity in activities_crud.get_activities_with_thumbnail(db):
            key = activity.map_thumbnail_path
            if key is not None and not storage.exists(activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA, key):
                activities_crud.set_activity_thumbnail_path(activity.id, None, db)
                logger.info(
                    "Thumbnail scheduler: cleared a thumbnail path whose blob is missing",
                    extra=core_logger.context(activity_id=activity.id),
                )

        activities_without_thumbnail = activities_crud.get_activities_without_thumbnail(db)

        if not activities_without_thumbnail:
            logger.debug("Thumbnail scheduler: no activities without thumbnail found")
            return

        logger.info(
            "Thumbnail scheduler: generating missing thumbnails",
            extra=core_logger.context(pending=len(activities_without_thumbnail)),
        )

        tile_url, background_color, api_key = resolve_tile_settings(db)

        activity_ids = [activity.id for activity in activities_without_thumbnail]
        # Batch-load MAP-stream waypoints through the streams CRUD (the ORM stays
        # confined there) as an {activity_id: waypoints} mapping.
        waypoints_by_activity_id = activity_streams_crud.get_gps_stream_waypoints_for_activities(activity_ids, db)

        generated = 0
        for activity in activities_without_thumbnail:
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

        logger.info(
            "Thumbnail scheduler pass complete",
            extra=core_logger.context(generated=generated, candidates=len(activities_without_thumbnail)),
        )
