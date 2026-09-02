"""Migration 9: move activity media blobs behind the ``StorageProvider``.

Activity photos were written straight to a configured media directory and the
absolute filesystem path was stored on the row, which is also how they were
addressed by the public static mount that used to serve them. They are now
stored through the platform ``StorageProvider`` under the ``activity_media``
area, keyed by a bare filename, and served only via the token-gated route.

The ``local`` backend maps that area to ``{DATA_DIR}/activity_media`` — the exact
directory the files already live in — so nothing has to be copied on a self-host
install: only the DB value is rewritten from the old absolute path to the key.
Installs already configured for object storage additionally have the bytes
uploaded, since the blob is not there yet.

A row whose file is missing is deleted, because the record can no longer resolve
to anything servable. Legacy values are recognised by containing a path
separator; keys never do, so the migration is idempotent.
"""

import os
from pathlib import Path

import jasil.runtime as platform_runtime
from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
import migrations.crud as migrations_crud
import modules.activities.activity_media.migration_service as activity_media_crud
import modules.activities.activity_media.migration_service as activity_media_signing

logger = core_logger.get_logger(__name__)

# Rows processed per DB round-trip; keeps memory bounded on large libraries.
_BATCH_SIZE = 200


def _media_area_dir() -> Path:
    """Return the local directory the media storage area maps to.

    Derived from the ``StorageProvider`` area convention (``{DATA_DIR}/{area}``)
    rather than a setting, so there is one definition of where a local media
    blob lives.
    """
    return Path(core_config.settings.DATA_DIR).resolve() / activity_media_signing.MEDIA_STORAGE_AREA


def _legacy_file(media_path: str) -> Path | None:
    """Resolve a legacy media path to an existing file inside the media directory.

    Args:
        media_path: The stored absolute path.

    Returns:
        The resolved file, or ``None`` when it is missing or escapes the media
        directory.
    """
    base = _media_area_dir()
    candidate = Path(media_path.replace("\\", "/"))
    # Migration 5 hard-coded an ``/app/backend/`` prefix, which does not exist on
    # a host install, so the stored path may not resolve here at all.
    for resolved in (candidate, base / candidate.name):
        try:
            full = resolved.resolve()
        except OSError:
            continue
        if full.is_file() and full.is_relative_to(base):
            return full
    return None


def process_migration_9(db: Session) -> None:
    """Rewrite legacy activity media paths to ``StorageProvider`` keys.

    Args:
        db: The SQLAlchemy database session.

    Returns:
        None.
    """
    logger.info("Started migration 9", extra=core_logger.context(console=True))

    storage = platform_runtime.get_active_platform().storage
    is_local = not core_config.settings.resolved_storage_uri.startswith("s3")
    processed_with_no_errors = True
    last_id = 0
    converted = 0
    dropped = 0

    while True:
        try:
            batch = activity_media_crud.get_media_with_legacy_path(db, after_id=last_id, limit=_BATCH_SIZE)
        except Exception as err:
            logger.error(
                f"Migration 9 - Error fetching activity media: {err}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
            processed_with_no_errors = False
            break

        if not batch:
            break

        for media in batch:
            if media.id is None:
                continue
            last_id = media.id
            try:
                source = _legacy_file(media.media_path)
                if source is None:
                    logger.warning(
                        f"Migration 9 - media {media.id} has no file at {media.media_path}; dropping the record",
                        extra=core_logger.context(console=True),
                    )
                    activity_media_crud.delete_activity_media(media.id, db)
                    dropped += 1
                    continue

                key = source.name
                if is_local:
                    # The area already resolves to this file's own directory, so
                    # rewriting the row is the whole migration. Re-saving would
                    # read and write the same bytes back over themselves.
                    expected = _media_area_dir() / key
                    if source != expected:
                        os.replace(source, expected)
                else:
                    storage.save(activity_media_signing.MEDIA_STORAGE_AREA, key, source.read_bytes())

                activity_media_crud.edit_activity_media_media_path(media.id, key, db)
                converted += 1
            except Exception as err:
                logger.error(
                    f"Migration 9 - Error processing activity media {media.id}: {err}",
                    exc_info=err,
                    extra=core_logger.context(console=True),
                )
                processed_with_no_errors = False
                continue

    logger.info(
        f"Migration 9 - rewrote {converted} activity media path(s) to storage keys, dropped {dropped} orphan(s)",
        extra=core_logger.context(console=True),
    )

    if processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(9, db)
        except Exception as err:
            logger.error(
                f"Migration 9 - Failed to set migration as executed: {err}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
    else:
        logger.warning(
            "Migration 9 - some records were not processed; migration will run again on next startup",
            extra=core_logger.context(console=True),
        )

    logger.info("Finished migration 9", extra=core_logger.context(console=True))
