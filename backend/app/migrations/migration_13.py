"""Migration 13: rename the stored files and folders named by an integer id to their UUID.

The conversion revisions record the old and new id of every converted row in ``uuid_migration_ids``. This migration
renames the stored files whose key is the integer id and then drops the table. It is safe to run again after a
failure: a key that is already a UUID is skipped.

Identity-provider icons are keyed by the provider id alone. Activities own three areas: the retained source files
(``processed/{id}.{ext}``), the map thumbnails (``{id}.webp``) and the media (``{id}_{suffix}``). The thumbnail and
media keys are also stored in a column, so those areas run in three phases: copy every mapped key to its UUID key,
rewrite the columns still holding the integer layout in one database transaction (only when no copy failed), then
delete every integer-layout key, orphans included. The integer layout is known only here; the new layout is built
by the modules.

Users own the profile photos (also stored in ``users.photo_path``, so the three phases above), the failed bulk-import
files, the staged profile exports and imports, and two drop folders on the local filesystem: the bulk-import folder
and the Strava-export folder, ``<root>/<integer user id>``. A folder is renamed to the UUID of its user. When the
UUID folder already exists the entries of the integer folder are moved into it, an entry already there stays where
it is, and a folder is never deleted (an emptied one is removed, which loses nothing). A folder whose user is gone
is left in place. Local storage lists, reads, copies and deletes both the plain and the opaque layout that
migration 11 moves, so this migration does not depend on migration 11 having run.
"""

import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
import migrations.crud as migrations_crud
import migrations.service as migrations_service
import modules.activities.activity.migration_service as activity_migration_service
import modules.activities.activity_file_storage.migration_service as activity_file_storage_migration_service
import modules.activities.activity_ingestion.migration_service as activity_ingestion_migration_service
import modules.activities.activity_media.migration_service as activity_media_migration_service
import modules.activities.activity_thumbnail.migration_service as activity_thumbnail_migration_service
import modules.auth.identity_providers.constants as idp_constants
import modules.strava.constants as strava_constants
import modules.strava.migration_service as strava_migration_service
import modules.users.users.migration_service as users_migration_service
import modules.users.users_profile.migration_service as users_profile_migration_service

logger = core_logger.get_logger(__name__)

#: Renames the stored files of one converted table, given the storage, the UUID of each old id and a session for the
#: columns that name a key; returns how many keys failed.
_Renamer = Callable[[platform_providers.StorageProvider, dict[int, uuid.UUID], Session], int]

#: The integer layouts of the activity keys. Each is matched against the whole key.
_INTEGER_FILE_KEY = re.compile(r"(?P<id>[0-9]+)(?P<extension>\.[a-z]+)")
_INTEGER_THUMBNAIL_KEY = re.compile(r"(?P<id>[0-9]+)\.webp")
_INTEGER_MEDIA_KEY = re.compile(r"(?P<id>[0-9]+)_(?P<suffix>[^/\\]+)")

#: The integer layouts of the user keys. Each is matched against the whole key.
_INTEGER_PHOTO_KEY = re.compile(r"(?P<id>[0-9]+)(?P<extension>\.[A-Za-z0-9]+)")
_INTEGER_FOLDER_KEY = re.compile(r"(?P<id>[0-9]+)/(?P<rest>.+)")
_INTEGER_EXPORT_KEY = re.compile(r"(?P<id>[0-9]+)\.zip")


def _log_failure(area: str, key: str, err: Exception) -> None:
    """Log a key that could not be renamed; the key is named, never its contents."""
    logger.error(
        f"Migration 13 - could not rename {area}/{key}: {err}",
        exc_info=err,
        extra=core_logger.context(console=True, storage_area=area, storage_key=key),
    )


def _rename_key(storage: platform_providers.StorageProvider, area: str, old_key: str, new_key: str | None) -> None:
    """Rename one stored object, or delete it when no row owns it.

    The copy is skipped when the new key already exists, so a run that stopped after the copy can be repeated.

    Args:
        storage: The platform storage provider.
        area: The storage area.
        old_key: The key named by the integer id.
        new_key: The key named by the UUID, or ``None`` when the row no longer exists.
    """
    if new_key is not None and not storage.exists(area, new_key):
        storage.copy(area, old_key, area, new_key)
    storage.delete(area, old_key)


def _guarded(area: str, rename: Callable[[], int]) -> int:
    """Run the rename of one area; an error that no key owns (a listing, the columns) counts as one failure."""
    try:
        return rename()
    except Exception as err:
        logger.error(
            f"Migration 13 - could not rename the keys of {area}: {err}",
            exc_info=err,
            extra=core_logger.context(console=True, storage_area=area),
        )
        return 1


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
        new_id = mapping.get(int(key))
        try:
            _rename_key(storage, area, key, None if new_id is None else str(new_id))
        except Exception as err:
            failed += 1
            _log_failure(area, key, err)
    return failed


def _rename_identity_provider_icons(
    storage: platform_providers.StorageProvider, mapping: dict[int, uuid.UUID], _db: Session
) -> int:
    """Rename the uploaded identity-provider icons to the UUID of their provider."""
    area = idp_constants.ICON_STORAGE_AREA
    return _guarded(area, lambda: _rename_keys_of_area(storage, area, mapping))


def _rename_activity_files(storage: platform_providers.StorageProvider, mapping: dict[int, uuid.UUID]) -> int:
    """Rename the retained activity source files, ``processed/{id}.{ext}``, to the UUID of their activity.

    A file whose activity is gone is deleted; every other key of the area (staged uploads, UUID keys) is left alone.

    Args:
        storage: The platform storage provider.
        mapping: The UUID of each old activity id.

    Returns:
        How many keys failed.
    """
    area = activity_file_storage_migration_service.ACTIVITY_FILE_STORAGE_AREA
    prefix = activity_file_storage_migration_service.processed_storage_key("")
    failed = 0
    for key in storage.list_keys(area, prefix):
        match = _INTEGER_FILE_KEY.fullmatch(key.removeprefix(prefix))
        if match is None or match["extension"] not in activity_file_storage_migration_service.STORED_EXTENSIONS:
            continue
        new_id = mapping.get(int(match["id"]))
        new_key = (
            None
            if new_id is None
            else activity_file_storage_migration_service.processed_storage_key(
                activity_file_storage_migration_service.activity_file_key(new_id, match["extension"])
            )
        )
        try:
            _rename_key(storage, area, key, new_key)
        except Exception as err:
            failed += 1
            _log_failure(area, key, err)
    return failed


def _rename_keys_named_by_a_column(
    storage: platform_providers.StorageProvider,
    area: str,
    mapping: dict[int, uuid.UUID],
    pattern: re.Pattern[str],
    new_key_of: Callable[[uuid.UUID, re.Match[str]], str],
    rewrite_columns: Callable[[Session], None],
    db: Session,
) -> int:
    """Rename the keys of an area that a database column also names, in three idempotent phases.

    The keys are copied first. The columns are rewritten, in one transaction, only when every copy succeeded, so a
    column never names a key that was not copied. The integer keys, orphans included, are deleted last, so a failed
    run leaves them for the next one.

    Args:
        storage: The platform storage provider.
        area: The storage area.
        mapping: The UUID of each old integer id.
        pattern: Matches an integer-layout key; its ``id`` group is the old integer id.
        new_key_of: Builds the UUID key from the new id and the match of the integer key.
        rewrite_columns: Stages the column rewrite in the session; this function commits it.
        db: The SQLAlchemy database session, with no transaction open.

    Returns:
        How many keys failed, or one when the columns could not be rewritten.
    """
    integer_keys = [
        (key, match) for key in storage.list_keys(area, "") if (match := pattern.fullmatch(key)) is not None
    ]
    failed = 0
    for key, match in integer_keys:
        new_id = mapping.get(int(match["id"]))
        if new_id is None:
            continue
        new_key = new_key_of(new_id, match)
        try:
            if not storage.exists(area, new_key):
                storage.copy(area, key, area, new_key)
        except Exception as err:
            failed += 1
            _log_failure(area, key, err)
    if failed:
        return failed

    try:
        rewrite_columns(db)
        db.commit()
    except Exception as err:
        db.rollback()
        logger.error(
            f"Migration 13 - could not rewrite the stored keys of {area}: {err}",
            exc_info=err,
            extra=core_logger.context(console=True, storage_area=area),
        )
        return 1

    for key, _match in integer_keys:
        try:
            storage.delete(area, key)
        except Exception as err:
            failed += 1
            _log_failure(area, key, err)
    return failed


def _rewrite_thumbnail_keys(db: Session) -> None:
    """Stage the activity thumbnail keys still in the integer layout as the key of their own activity."""
    changes = [
        (activity_id, key, activity_thumbnail_migration_service.thumbnail_key(activity_id))
        for activity_id, key in activity_migration_service.get_activity_thumbnail_keys(db)
        if _INTEGER_THUMBNAIL_KEY.fullmatch(key)
    ]
    activity_migration_service.replace_activity_thumbnail_keys(changes, db)


def _rewrite_media_paths(db: Session) -> None:
    """Stage the media paths still in the integer layout as the key of their own activity, keeping the suffix."""
    changes = []
    for media in activity_media_migration_service.get_all_activity_media(db):
        match = _INTEGER_MEDIA_KEY.fullmatch(media.media_path)
        if match is not None:
            changes.append(
                (
                    media.id,
                    media.media_path,
                    activity_media_migration_service.media_key(media.activity_id, match["suffix"]),
                )
            )
    activity_media_migration_service.replace_activity_media_paths(changes, db)


def _rename_activity_blobs(
    storage: platform_providers.StorageProvider, mapping: dict[int, uuid.UUID], db: Session
) -> int:
    """Rename the activity source files, map thumbnails and media to the UUID of their activity."""
    thumbnail_area = activity_thumbnail_migration_service.THUMBNAIL_STORAGE_AREA
    media_area = activity_media_migration_service.MEDIA_STORAGE_AREA
    return (
        _guarded(
            activity_file_storage_migration_service.ACTIVITY_FILE_STORAGE_AREA,
            lambda: _rename_activity_files(storage, mapping),
        )
        + _guarded(
            thumbnail_area,
            lambda: _rename_keys_named_by_a_column(
                storage,
                thumbnail_area,
                mapping,
                _INTEGER_THUMBNAIL_KEY,
                lambda new_id, _match: activity_thumbnail_migration_service.thumbnail_key(new_id),
                _rewrite_thumbnail_keys,
                db,
            ),
        )
        + _guarded(
            media_area,
            lambda: _rename_keys_named_by_a_column(
                storage,
                media_area,
                mapping,
                _INTEGER_MEDIA_KEY,
                lambda new_id, match: activity_media_migration_service.media_key(new_id, match["suffix"]),
                _rewrite_media_paths,
                db,
            ),
        )
    )


def _rename_matching_keys(
    storage: platform_providers.StorageProvider,
    area: str,
    mapping: dict[int, uuid.UUID],
    pattern: re.Pattern[str],
    new_key_of: Callable[[uuid.UUID, re.Match[str]], str],
) -> int:
    """Rename every key of an area that matches an integer layout; no column names these keys.

    A key whose integer has no row is an orphan of a deleted row and is deleted; every other key is left alone.

    Args:
        storage: The platform storage provider.
        area: The storage area.
        mapping: The UUID of each old integer id.
        pattern: Matches an integer-layout key; its ``id`` group is the old integer id.
        new_key_of: Builds the UUID key from the new id and the match of the integer key.

    Returns:
        How many keys failed.
    """
    failed = 0
    for key in storage.list_keys(area, ""):
        match = pattern.fullmatch(key)
        if match is None:
            continue
        new_id = mapping.get(int(match["id"]))
        try:
            _rename_key(storage, area, key, None if new_id is None else new_key_of(new_id, match))
        except Exception as err:
            failed += 1
            _log_failure(area, key, err)
    return failed


def _rewrite_photo_keys(mapping: dict[int, uuid.UUID]) -> Callable[[Session], None]:
    """Build the column rewrite of ``users.photo_path``: the integer key of a user becomes the key of their UUID."""

    def rewrite(db: Session) -> None:
        changes = []
        for user_id, key in users_migration_service.get_stored_photo_keys(db):
            match = None if key is None else _INTEGER_PHOTO_KEY.fullmatch(key)
            if key is not None and match is not None and mapping.get(int(match["id"])) == user_id:
                changes.append((user_id, key, users_migration_service.photo_key(user_id, match["extension"])))
        users_migration_service.replace_photo_keys(changes, db)

    return rewrite


def _log_folder_failure(folder: Path, err: Exception) -> None:
    """Log a drop folder that could not be moved; the path is named, never its contents."""
    logger.error(
        f"Migration 13 - could not rename the folder {folder}: {err}",
        exc_info=err,
        extra=core_logger.context(console=True, folder=str(folder)),
    )


def _raise(err: OSError) -> None:
    """Fail the walk on a folder it cannot read, which ``os.walk`` would skip."""
    raise err


def _move_folder(source: Path, target: Path) -> None:
    """Move a drop folder to its new name, merging into the target when it already exists.

    Nothing is overwritten and no file is deleted: an entry the target already holds stays in the source folder,
    which is removed only once it is empty.

    Args:
        source: The folder named by the integer id.
        target: The folder named by the UUID.

    Raises:
        OSError: When an entry or a folder cannot be moved.
    """
    if not target.exists():
        os.rename(source, target)
        return
    for current, _folders, files in os.walk(source, onerror=_raise):
        current_path = Path(current)
        destination = target / current_path.relative_to(source)
        destination.mkdir(parents=True, exist_ok=True)
        for name in files:
            if not (destination / name).exists():
                os.rename(current_path / name, destination / name)
            else:
                logger.warning(
                    f"Migration 13 - {current_path / name} was kept: {destination / name} already exists",
                    extra=core_logger.context(console=True),
                )
    for current, _folders, _files in os.walk(source, topdown=False):
        try:
            Path(current).rmdir()
        except OSError:
            continue


def _rename_drop_folders(root: Path, new_folder_of: Callable[[uuid.UUID], str], mapping: dict[int, uuid.UUID]) -> int:
    """Rename the ``<root>/<integer user id>`` folders to the folder of their UUID.

    A folder whose user is gone, and anything that is not an integer folder, is left alone.

    Args:
        root: The directory holding the integer folders.
        new_folder_of: Builds the UUID folder from the new id.
        mapping: The UUID of each old integer id.

    Returns:
        How many folders failed.
    """
    if not root.is_dir():
        return 0
    try:
        folders = sorted(root.iterdir())
    except OSError as err:
        _log_folder_failure(root, err)
        return 1
    failed = 0
    for folder in folders:
        if not (folder.name.isascii() and folder.name.isdecimal() and folder.is_dir()):
            continue
        new_id = mapping.get(int(folder.name))
        if new_id is None:
            continue
        try:
            _move_folder(folder, Path(new_folder_of(new_id)))
        except OSError as err:
            failed += 1
            _log_folder_failure(folder, err)
    return failed


def _rename_user_blobs(storage: platform_providers.StorageProvider, mapping: dict[int, uuid.UUID], db: Session) -> int:
    """Rename the profile photos, failed bulk-import files, staged archives and drop folders to the UUID of their user."""
    photo_area = users_migration_service.USER_IMAGE_STORAGE_AREA
    errors_area = activity_ingestion_migration_service.BULK_IMPORT_ERROR_STORAGE_AREA
    export_area = users_profile_migration_service.EXPORT_STAGING_AREA
    import_area = users_profile_migration_service.IMPORT_STAGING_AREA
    failed = (
        _guarded(
            photo_area,
            lambda: _rename_keys_named_by_a_column(
                storage,
                photo_area,
                mapping,
                _INTEGER_PHOTO_KEY,
                lambda new_id, match: users_migration_service.photo_key(new_id, match["extension"]),
                _rewrite_photo_keys(mapping),
                db,
            ),
        )
        + _guarded(
            errors_area,
            lambda: _rename_matching_keys(
                storage,
                errors_area,
                mapping,
                _INTEGER_FOLDER_KEY,
                lambda new_id, match: (
                    activity_ingestion_migration_service.bulk_import_error_prefix(new_id) + match["rest"]
                ),
            ),
        )
        + _guarded(
            export_area,
            lambda: _rename_matching_keys(
                storage,
                export_area,
                mapping,
                _INTEGER_EXPORT_KEY,
                lambda new_id, _match: users_profile_migration_service.export_staged_key(new_id),
            ),
        )
        + _guarded(
            import_area,
            lambda: _rename_matching_keys(
                storage,
                import_area,
                mapping,
                _INTEGER_FOLDER_KEY,
                lambda new_id, match: users_profile_migration_service.import_staged_prefix(new_id) + match["rest"],
            ),
        )
    )
    folders = (
        (Path(core_config.FILES_BULK_IMPORT_DIR), core_config.bulk_import_dir_for),
        (
            Path(core_config.settings.FILES_DIR) / strava_constants.BULK_IMPORT_DIR_NAME,
            strava_migration_service.drop_directory_for,
        ),
    )
    return failed + sum(_rename_drop_folders(root, new_folder_of, mapping) for root, new_folder_of in folders)


#: The renamer of each converted table that has stored files.
_RENAMERS: dict[str, _Renamer] = {
    "identity_providers": _rename_identity_provider_icons,
    "activities": _rename_activity_blobs,
    "users": _rename_user_blobs,
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

    failed = sum(_RENAMERS[table](storage, mapping, db) for table, mapping in mappings.items())
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
