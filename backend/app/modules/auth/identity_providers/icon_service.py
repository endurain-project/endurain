"""The uploaded icon of an identity provider: upload, removal and serving."""

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.crud as idp_crud

logger = core_logger.get_logger(__name__)


def _storage_key(idp_id: int) -> str:
    """Return the storage key of a provider's icon."""
    return str(idp_id)


def upload_icon(idp_id: int, data: bytes, storage: platform_providers.StorageProvider, db: Session) -> int:
    """Save a provider's icon and mark it as set.

    The blob is written before the provider row is locked, so storage latency never holds the lock. A blob
    without the flag is invisible, whereas a flag without a blob would point the login page at nothing, so the
    flag is committed last. The stored content type is the one detected from the bytes, not the one the client
    claimed.

    Args:
        idp_id: The provider the icon belongs to.
        data: The uploaded image, already validated as an image.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The provider version that identifies the icon.

    Raises:
        NotFoundError: If the provider does not exist.
        PayloadTooLargeError: If the image exceeds the icon size cap.
        UnsupportedMediaTypeError: If the image is not a PNG, JPEG, GIF or WebP.
    """
    if not idp_crud.identity_provider_exists(idp_id, db):
        raise core_exceptions.NotFoundError("Identity provider not found")
    if len(data) > idp_constants.ICON_MAX_BYTES:
        raise core_exceptions.PayloadTooLargeError("Identity provider icon is too large")
    media_type = core_file_uploads.sniff_image_type(data)
    if media_type is None:
        raise core_exceptions.UnsupportedMediaTypeError("Identity provider icon must be a PNG, JPEG, GIF or WebP image")
    storage.save(idp_constants.ICON_STORAGE_AREA, _storage_key(idp_id), data, media_type)
    version = idp_crud.set_icon_uploaded(idp_id, True, db)
    if version is None:
        # The provider was deleted while the blob was being written.
        delete_blob(idp_id, storage)
        raise core_exceptions.NotFoundError("Identity provider not found")
    db.commit()
    logger.info("Identity provider icon uploaded", extra=core_logger.context(idp_id=idp_id))
    return version


def delete_icon(idp_id: int, storage: platform_providers.StorageProvider, db: Session) -> None:
    """Remove a provider's uploaded icon and mark it as unset.

    The flag is cleared and committed first, so the icon stops being served at once and the provider row is not
    locked while storage is called. The blob is deleted afterwards; if that fails it is an unreferenced leftover
    that the next upload overwrites.

    Args:
        idp_id: The provider the icon belongs to.
        storage: The platform storage provider.
        db: Database session.

    Raises:
        NotFoundError: If the provider does not exist.
    """
    if idp_crud.set_icon_uploaded(idp_id, False, db) is None:
        raise core_exceptions.NotFoundError("Identity provider not found")
    db.commit()
    delete_blob(idp_id, storage)
    logger.info("Identity provider icon deleted", extra=core_logger.context(idp_id=idp_id))


def delete_blob(idp_id: int, storage: platform_providers.StorageProvider) -> None:
    """Delete an icon blob, logging instead of failing: the flag already decides whether it is served.

    Args:
        idp_id: The provider the icon belongs to.
        storage: The platform storage provider.
    """
    try:
        storage.delete(idp_constants.ICON_STORAGE_AREA, _storage_key(idp_id))
    except Exception as err:
        logger.warning(
            "Identity provider icon blob could not be deleted", extra=core_logger.context(idp_id=idp_id), exc_info=err
        )


def get_public_icon(slug: str, db: Session) -> tuple[int, int] | None:
    """Return the id and icon version of a provider that has an uploaded icon.

    A disabled provider's icon is served too: the admin list shows it, and it is one admin-chosen logo.

    Args:
        slug: The provider slug.
        db: Database session.

    Returns:
        The provider id and its version (the icon's entity tag), or None when there is no icon to serve.
    """
    state = idp_crud.get_identity_provider_by_slug(slug.lower(), db)
    # End the read transaction: the caller may go on to read storage.
    db.rollback()
    if state is None or not state.icon_uploaded:
        return None
    return state.id, state.version


def read_icon(idp_id: int, storage: platform_providers.StorageProvider) -> tuple[bytes, str] | None:
    """Return a provider's uploaded icon.

    Args:
        idp_id: The provider the icon belongs to.
        storage: The platform storage provider.

    Returns:
        The image bytes and their media type, or None when no icon is stored.
    """
    data = storage.get(idp_constants.ICON_STORAGE_AREA, _storage_key(idp_id))
    if data is None:
        return None
    # Bytes whose type cannot be detected are served as PNG.
    return data, core_file_uploads.sniff_image_type(data) or "image/png"
