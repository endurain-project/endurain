"""The login page photo: upload, removal and serving."""

import jasil.providers as platform_providers
from fastapi import UploadFile
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.service as server_settings_service

logger = core_logger.get_logger(__name__)


#: Magic-number prefixes of the image formats the upload validator accepts, with their media type.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _sniff_image_type(data: bytes) -> str | None:
    """Return the media type of image bytes from their magic number.

    Args:
        data: The image bytes.

    Returns:
        The media type, or None when the format is not recognised.
    """
    for signature, media_type in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def upload_login_photo(file: UploadFile, storage: platform_providers.StorageProvider, db: Session) -> None:
    """Save the custom login page photo and mark it as set.

    The blob is written before the settings row is locked, so storage latency never
    holds the lock. A blob without the flag is invisible, whereas a flag without a
    blob would point the login page at nothing, so the flag is committed last. The
    stored content type is the one detected from the bytes, not the one the client
    claimed.

    Args:
        file: The uploaded image.
        storage: The platform storage provider.
        db: Database session.

    Raises:
        DomainError: If the upload fails validation or exceeds the login-photo size cap.
        ServiceUnavailableError: If the settings row does not exist.
    """
    data = core_file_uploads.read_validated_upload_sync(file, kind=core_file_uploads.UploadKind.IMAGE)
    if len(data) > server_settings_constants.LOGIN_PHOTO_MAX_BYTES:
        raise core_exceptions.PayloadTooLargeError("Login photo is too large")
    media_type = _sniff_image_type(data)
    if media_type is None:
        raise core_exceptions.UnsupportedMediaTypeError("Login photo must be a PNG, JPEG, GIF or WebP image")
    storage.save(
        server_settings_constants.LOGIN_PHOTO_STORAGE_AREA,
        server_settings_constants.LOGIN_PHOTO_STORAGE_KEY,
        data,
        media_type,
    )
    server_settings_crud.set_login_photo(True, db)
    db.commit()
    logger.info("Login photo uploaded")


def delete_login_photo(storage: platform_providers.StorageProvider, db: Session) -> None:
    """Remove the custom login page photo and mark it as unset.

    The flag is cleared and committed first, so the photo stops being served at once
    and the settings row is not locked while storage is called. The blob is deleted
    afterwards; if that fails it is an unreferenced leftover that the next upload
    overwrites.

    Args:
        storage: The platform storage provider.
        db: Database session.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    server_settings_crud.set_login_photo(False, db)
    db.commit()
    try:
        storage.delete(
            server_settings_constants.LOGIN_PHOTO_STORAGE_AREA, server_settings_constants.LOGIN_PHOTO_STORAGE_KEY
        )
    except Exception:
        logger.warning("Login photo blob could not be deleted; it is no longer served", exc_info=True)
    logger.info("Login photo deleted")


def get_login_photo_version(db: Session) -> int | None:
    """Return the settings version that identifies the current login photo.

    Every photo upload or removal bumps the settings version, so it serves as the
    photo's entity tag without reading the image.

    Args:
        db: Database session.

    Returns:
        The version, or None when no custom photo is set.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    settings = server_settings_service.get_server_settings(db)
    # End the read transaction: the caller may go on to read storage.
    db.rollback()
    return settings.version if settings.login_photo_set else None


def read_login_photo(storage: platform_providers.StorageProvider) -> tuple[bytes, str] | None:
    """Return the custom login page photo.

    Args:
        storage: The platform storage provider.

    Returns:
        The image bytes and their media type, or None when no photo is stored.
    """
    data = storage.get(
        server_settings_constants.LOGIN_PHOTO_STORAGE_AREA, server_settings_constants.LOGIN_PHOTO_STORAGE_KEY
    )
    if data is None:
        return None
    # Bytes whose type cannot be detected are served as PNG.
    return data, _sniff_image_type(data) or "image/png"
