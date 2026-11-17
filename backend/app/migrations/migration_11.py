"""Migration 11: move local storage objects into the plain area layout."""

from pathlib import Path

import jasil.runtime as platform_runtime
from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
import migrations.service as migrations_service
import module_registry as runtime_module_registry
import modules.activities.activity_thumbnail.scheduled_jobs as activity_thumbnail_scheduled_jobs

logger = core_logger.get_logger(__name__)


def _plain_file_exists(area: str, key: str) -> bool:
    """Return whether an object's plain-layout destination is already a file.

    Args:
        area: The storage area.
        key: The logical storage key.

    Returns:
        Whether ``{DATA_DIR}/{area}/{key}`` is a regular file.
    """
    destination = Path(core_config.settings.DATA_DIR).resolve() / area / key
    if destination.resolve() != destination:
        raise ValueError(f"Plain storage path resolves through a symbolic link: {area}/{key}")
    return destination.is_file()


def process_migration_11(db: Session) -> None:
    """Move objects in the local provider layout into their plain area paths.

    The migration is a no-op for non-local storage. In local storage, objects
    already present at their plain path are left alone; objects visible only in
    Jasil's object layout are streamed through the storage provider, which writes
    the plain file and removes the old object.

    Args:
        db: The SQLAlchemy database session.
    """
    logger.info("Started migration 11", extra=core_logger.context(console=True))

    try:
        if not core_config.settings.resolved_storage_uri.startswith("local://"):
            logger.info("Migration 11 - skipped for non-local storage", extra=core_logger.context(console=True))
            _mark_executed(db)
            return
        storage = platform_runtime.get_active_platform().storage
    except Exception as err:
        logger.error(
            f"Migration 11 - could not initialize local storage: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        return

    areas = runtime_module_registry.storage_plain_areas()
    processed_with_no_errors = True
    moved = 0
    already_plain = 0

    for area in sorted(areas):
        try:
            keys = sorted(key for key, _ in storage.iter_objects(area))
        except Exception as err:
            logger.error(
                f"Migration 11 - could not list objects in {area}: {err}",
                exc_info=err,
                extra=core_logger.context(console=True, storage_area=area),
            )
            processed_with_no_errors = False
            continue

        for key in keys:
            try:
                if _plain_file_exists(area, key):
                    already_plain += 1
                    continue

                with storage.open_stream(area, key) as source:
                    storage.save_stream(area, key, source)
                moved += 1
            except Exception as err:
                logger.error(
                    f"Migration 11 - could not move {area}/{key}: {err}",
                    exc_info=err,
                    extra=core_logger.context(console=True, storage_area=area, storage_key=key),
                )
                processed_with_no_errors = False

    logger.info(
        f"Migration 11 - moved {moved} object(s), found {already_plain} already plain",
        extra=core_logger.context(console=True),
    )

    if processed_with_no_errors:
        _mark_executed(db)
        activity_thumbnail_scheduled_jobs.schedule_full_thumbnail_regeneration()
    else:
        logger.warning(
            "Migration 11 - some objects were not moved; migration will retry on next startup",
            extra=core_logger.context(console=True),
        )

    logger.info("Finished migration 11", extra=core_logger.context(console=True))


def _mark_executed(db: Session) -> None:
    """Mark migration 11 complete, logging database failures."""
    try:
        migrations_service.mark_executed(11, db)
    except Exception as err:
        logger.error(
            f"Migration 11 - failed to set migration as executed: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
