"""Migration 8: re-encode legacy PNG thumbnails to WebP and store storage keys.

Pre-PoC thumbnails were PNGs written to disk, with their absolute filesystem
path stored on the activity. The thumbnail PoC stores WebP
blobs through the platform ``StorageProvider`` addressed by a bare key
(e.g. ``42.webp``). This migration re-encodes each existing PNG to WebP, saves it
through the storage provider, and rewrites the DB value from the old path to the
key — preserving existing thumbnails without re-fetching map tiles. A thumbnail
whose file is missing or cannot be re-encoded has its path cleared so the hourly
backfill regenerates it. Legacy values are recognised by containing a path
separator; new keys never do, so the migration is idempotent.
"""

from io import BytesIO
from pathlib import Path

import jasil.runtime as platform_runtime
from PIL import Image
from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.crud as migrations_crud
import modules.activities.activity.migration_service as activities_crud
import modules.activities.activity_thumbnail.migration_service as activity_thumbnail_render
import modules.activities.activity_thumbnail.migration_service as activity_thumbnail_signing

logger = core_logger.get_logger(__name__)

# Rows processed per DB round-trip; keeps memory bounded on large libraries.
_BATCH_SIZE = 200
_WEBP_QUALITY = 75
# Encoder effort (0-6): 6 = smallest file at a given quality (matches the renderer).
_WEBP_METHOD = 6


def _reencode_to_webp(source: Path) -> bytes | None:
    """Re-encode a PNG file to WebP bytes at the standard thumbnail size.

    Args:
        source: Path to the existing PNG thumbnail.

    Returns:
        WebP-encoded bytes, or ``None`` when the file cannot be read/decoded.
    """
    try:
        with Image.open(source) as image:
            resized = image.convert("RGB").resize(
                (activity_thumbnail_render.THUMBNAIL_WIDTH, activity_thumbnail_render.THUMBNAIL_HEIGHT)
            )
            buffer = BytesIO()
            resized.save(buffer, "WEBP", quality=_WEBP_QUALITY, method=_WEBP_METHOD)
            return buffer.getvalue()
    except (OSError, ValueError) as err:
        logger.warning(f"Migration 8 - could not re-encode {source}: {err}")
        return None


def process_migration_8(db: Session) -> None:
    """Re-encode legacy PNG thumbnails to WebP and store their storage keys.

    Args:
        db: The SQLAlchemy database session.

    Returns:
        None.
    """
    logger.info("Started migration 8", extra=core_logger.context(console=True))

    storage = platform_runtime.get_active_platform().storage
    processed_with_no_errors = True
    last_id = 0
    converted = 0
    cleared = 0

    while True:
        try:
            batch = activities_crud.get_activities_with_legacy_thumbnail_path(db, after_id=last_id, limit=_BATCH_SIZE)
        except Exception as err:
            logger.error(
                f"Migration 8 - Error fetching activities: {err}", exc_info=err, extra=core_logger.context(console=True)
            )
            return

        if not batch:
            break

        for activity in batch:
            # Always advance the cursor so a failing row cannot loop forever; it
            # is retried on the next startup (the migration stays unexecuted).
            last_id = activity.id
            legacy_path = activity.map_thumbnail_path
            if not legacy_path:
                continue
            try:
                key = activity_thumbnail_signing.thumbnail_key(activity.id)
                source = Path(legacy_path)
                data = _reencode_to_webp(source) if source.is_file() else None
                if data is not None:
                    storage.save(
                        activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA,
                        key,
                        data,
                        activity_thumbnail_render.THUMBNAIL_CONTENT_TYPE,
                    )
                    activities_crud.set_activity_thumbnail_path(activity.id, key, db)
                    source.unlink(missing_ok=True)
                    converted += 1
                else:
                    # Missing or unreadable source: clear so the backfill regenerates.
                    activities_crud.set_activity_thumbnail_path(activity.id, None, db)
                    source.unlink(missing_ok=True)
                    cleared += 1
            except Exception as err:
                processed_with_no_errors = False
                logger.error(
                    f"Migration 8 - Error processing activity {activity.id}: {err}",
                    exc_info=err,
                    extra=core_logger.context(console=True),
                )

    if processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(8, db)
        except Exception as err:
            logger.error(
                f"Migration 8 - Failed to set migration as executed: {err}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
            return
    else:
        logger.error(
            "Migration 8 failed to process all thumbnails. Will try again later.",
            extra=core_logger.context(console=True),
        )

    logger.info(
        f"Finished migration 8 (converted {converted}, cleared {cleared})", extra=core_logger.context(console=True)
    )
