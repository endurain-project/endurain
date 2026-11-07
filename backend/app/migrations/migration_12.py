"""Migration 12: strip metadata from the images already in storage.

Uploaded images used to be stored byte for byte, so the EXIF (including GPS), XMP and PNG text of an
original reached everyone who could see the image. Every stored image is re-encoded without it, and
profile photos are reduced to the size cap new uploads get.
"""

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import migrations.service as migrations_service
import modules.activities.activity_media.migration_service as activity_media_migration_service
import modules.auth.identity_providers.constants as idp_constants
import modules.server_settings.constants as server_settings_constants
import modules.users.users.constants as users_constants
import modules.users.users.migration_service as users_migration_service

logger = core_logger.get_logger(__name__)

#: A stored image: its storage area, its key and the longest edge it is reduced to, if any.
_Target = tuple[str, str, int | None]


def _collect_targets(storage: platform_providers.StorageProvider, db: Session) -> list[_Target]:
    """List every stored image the migration rewrites.

    The database reads end before any storage call is made.

    Args:
        storage: The platform storage provider.
        db: The SQLAlchemy database session.

    Returns:
        The images to rewrite.
    """
    targets: list[_Target] = [
        (users_migration_service.USER_IMAGE_STORAGE_AREA, photo_key, users_constants.USER_IMAGE_MAX_DIMENSION)
        for _, photo_key in users_migration_service.get_stored_photo_keys(db)
        if photo_key
    ]
    targets.extend(
        (activity_media_migration_service.MEDIA_STORAGE_AREA, media.media_path, None)
        for media in activity_media_migration_service.get_all_activity_media(db)
    )
    db.rollback()

    targets.append(
        (server_settings_constants.LOGIN_PHOTO_STORAGE_AREA, server_settings_constants.LOGIN_PHOTO_STORAGE_KEY, None)
    )
    targets.extend(
        (idp_constants.ICON_STORAGE_AREA, key, None) for key in storage.list_keys(idp_constants.ICON_STORAGE_AREA, "")
    )
    return targets


def _strip_stored_image(storage: platform_providers.StorageProvider, target: _Target) -> bool:
    """Rewrite one stored image without its metadata, under the same key and content type.

    Args:
        storage: The platform storage provider.
        target: The area, key and size cap of the image.

    Returns:
        Whether an image was rewritten; False when nothing is stored under the key.

    Raises:
        InvalidInputError: When the stored bytes are not a rewritable image.
    """
    area, key, max_dimension = target
    data = storage.get(area, key)
    if data is None:
        return False
    media_type = core_file_uploads.sniff_image_type(data)
    if media_type is None:
        raise core_exceptions.InvalidInputError("The stored object is not a recognised image")
    storage.save(area, key, core_file_uploads.strip_image_metadata(data, max_dimension=max_dimension), media_type)
    return True


def process_migration_12(db: Session) -> None:
    """Re-encode every stored image without its metadata.

    Covers profile photos (also reduced to the photo size cap), activity photos, the login photo and
    identity-provider icons. Activity media content hashes are left as recorded, so a re-import of the
    original photo is still recognised as a duplicate. An image that cannot be read or rewritten is
    logged and left as it is. The migration is marked executed once every image was tried, because a
    re-run would re-encode the images already rewritten.

    Args:
        db: The SQLAlchemy database session.
    """
    logger.info("Started migration 12", extra=core_logger.context(console=True))

    try:
        storage = platform_runtime.get_active_platform().storage
        targets = _collect_targets(storage, db)
    except Exception as err:
        logger.error(
            f"Migration 12 - could not list the stored images: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        return

    rewritten = 0
    failed = 0
    for target in targets:
        try:
            if _strip_stored_image(storage, target):
                rewritten += 1
        except Exception as err:
            failed += 1
            logger.error(
                f"Migration 12 - could not strip {target[0]}/{target[1]}: {err}",
                exc_info=err,
                extra=core_logger.context(console=True, storage_area=target[0], storage_key=target[1]),
            )

    logger.info(
        f"Migration 12 - rewrote {rewritten} image(s), {failed} failed",
        extra=core_logger.context(console=True),
    )

    try:
        migrations_service.mark_executed(12, db)
    except Exception as err:
        logger.error(
            f"Migration 12 - failed to set migration as executed: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )

    logger.info("Finished migration 12", extra=core_logger.context(console=True))
