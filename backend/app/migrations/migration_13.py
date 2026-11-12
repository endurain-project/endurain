"""Migration 13: rename the stored files named by an integer id to their UUID.

The conversion revisions record the old and new id of every converted row in ``uuid_migration_ids``. This migration
renames the stored files whose key is the integer id and then drops the table. It is safe to run again after a
failure: a key that is already a UUID is skipped.
"""

import uuid
from collections.abc import Callable

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.crud as migrations_crud
import migrations.service as migrations_service
import modules.auth.identity_providers.constants as idp_constants

logger = core_logger.get_logger(__name__)

#: Renames the stored files of one converted table, given the storage and the UUID of each old id; returns how many
#: keys failed.
_Renamer = Callable[[platform_providers.StorageProvider, dict[int, uuid.UUID]], int]


def _rename_key(storage: platform_providers.StorageProvider, area: str, old_key: str, new_id: uuid.UUID | None) -> None:
    """Rename one stored object to the UUID, or delete it when no row owns it.

    The copy is skipped when the UUID key already exists, so a run that stopped after the copy can be repeated.

    Args:
        storage: The platform storage provider.
        area: The storage area.
        old_key: The key named by the integer id.
        new_id: The UUID of the row the integer named, or ``None`` when the row no longer exists.
    """
    if new_id is not None:
        new_key = str(new_id)
        if not storage.exists(area, new_key):
            storage.copy(area, old_key, area, new_key)
    storage.delete(area, old_key)


def _rename_keys_of_area(storage: platform_providers.StorageProvider, area: str, mapping: dict[int, uuid.UUID]) -> int:
    """Rename every key of a storage area that is an integer; keys that are not integers are left alone.

    A key whose integer has no row is an orphan of a deleted row and is deleted.

    Args:
        storage: The platform storage provider.
        area: The storage area.
        mapping: The UUID of each old integer id.

    Returns:
        How many keys failed.
    """
    failed = 0
    for key in storage.list_keys(area, ""):
        if not (key.isascii() and key.isdecimal()):
            continue
        try:
            _rename_key(storage, area, key, mapping.get(int(key)))
        except Exception as err:
            failed += 1
            logger.error(
                f"Migration 13 - could not rename {area}/{key}: {err}",
                exc_info=err,
                extra=core_logger.context(console=True, storage_area=area, storage_key=key),
            )
    return failed


def _rename_identity_provider_icons(storage: platform_providers.StorageProvider, mapping: dict[int, uuid.UUID]) -> int:
    """Rename the uploaded identity-provider icons to the UUID of their provider."""
    return _rename_keys_of_area(storage, idp_constants.ICON_STORAGE_AREA, mapping)


#: The renamer of each converted table that has stored files.
_RENAMERS: dict[str, _Renamer] = {
    "identity_providers": _rename_identity_provider_icons,
}


def process_migration_13(db: Session) -> None:
    """Rename the stored files named by an integer id and drop the recorded ids.

    The recorded ids are read first and the read transaction ends before any storage call. When every key was
    renamed, the table is dropped and the migration is marked executed in one commit. A failure is logged with the
    key, never its contents, and leaves the table and the migration as they are, so the next start retries.

    Args:
        db: The SQLAlchemy database session.
    """
    logger.info("Started migration 13", extra=core_logger.context(console=True))

    try:
        storage = platform_runtime.get_active_platform().storage
        mappings = {table: migrations_crud.get_uuid_migration_ids(table, db) for table in _RENAMERS}
        db.rollback()
    except Exception as err:
        db.rollback()
        logger.error(
            f"Migration 13 - could not read the recorded ids: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        return

    failed = sum(_RENAMERS[table](storage, mapping) for table, mapping in mappings.items())
    if failed:
        logger.error(
            f"Migration 13 - {failed} stored file(s) could not be renamed; it will run again at the next start",
            extra=core_logger.context(console=True),
        )
        return

    try:
        migrations_crud.drop_uuid_migration_ids(db)
        migrations_service.mark_executed(13, db)
    except Exception as err:
        db.rollback()
        logger.error(
            f"Migration 13 - failed to finish: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        return

    logger.info("Finished migration 13", extra=core_logger.context(console=True))
