"""The uploaded icon of an identity provider: upload, removal and serving."""

import jasil.audit as jasil_audit
import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.blob_sweep as core_blob_sweep
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.crud as idp_crud

logger = core_logger.get_logger(__name__)


def _storage_key(idp_id: int) -> str:
    """Return the storage key of a provider's icon."""
    return str(idp_id)


def _stage_icon_audit(idp_id: int, db: Session) -> None:
    """Stage ``auth.identity_provider.update`` for an icon change, in the transaction that commits the flag.

    Args:
        idp_id: The provider whose icon changed.
        db: Database session.
    """
    jasil_audit.stage(
        db,
        idp_audit_actions.IDENTITY_PROVIDER_UPDATE,
        target_type="identity_provider",
        target_id=str(idp_id),
        details=idp_audit_actions.IdentityProviderUpdateDetails(changed_fields=["icon_uploaded"]),
    )


def upload_icon(idp_id: int, data: bytes, storage: platform_providers.StorageProvider, db: Session) -> int:
    """Save a provider's icon and mark it as set.

    The read transaction that checked the provider is ended before the blob is written, so storage latency
    holds neither a connection nor the provider row. A blob without the flag is invisible, whereas a flag
    without a blob would point the login page at nothing, so the flag is committed last. The stored content type
    is the one detected from the bytes, not the one the client claimed. The image is re-encoded without its
    metadata.

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
        InvalidInputError: If the image cannot be decoded for the metadata strip.
    """
    if not idp_crud.identity_provider_exists(idp_id, db):
        raise core_exceptions.NotFoundError("Identity provider not found")
    if len(data) > idp_constants.ICON_MAX_BYTES:
        raise core_exceptions.PayloadTooLargeError("Identity provider icon is too large")
    media_type = core_file_uploads.sniff_image_type(data)
    if media_type is None:
        raise core_exceptions.UnsupportedMediaTypeError("Identity provider icon must be a PNG, JPEG, GIF or WebP image")
    # End the read transaction: storage is a network call.
    db.rollback()
    storage.save(
        idp_constants.ICON_STORAGE_AREA, _storage_key(idp_id), core_file_uploads.strip_image_metadata(data), media_type
    )
    version = idp_crud.set_icon_uploaded(idp_id, True, db)
    if version is None:
        # The provider was deleted while the blob was being written. End the transaction before storage is called.
        db.rollback()
        delete_blob(idp_id, storage)
        raise core_exceptions.NotFoundError("Identity provider not found")
    _stage_icon_audit(idp_id, db)
    db.commit()
    logger.info("Identity provider icon uploaded", extra=core_logger.context(idp_id=idp_id))
    return version


def delete_icon(idp_id: int, storage: platform_providers.StorageProvider, db: Session) -> None:
    """Remove a provider's uploaded icon and mark it as unset.

    The flag is cleared and committed first, so the icon stops being served at once and the provider row is not
    locked while storage is called. The blob is deleted afterwards; if that fails it is an unreferenced leftover
    that the next upload overwrites or the icon sweep removes.

    Args:
        idp_id: The provider the icon belongs to.
        storage: The platform storage provider.
        db: Database session.

    Raises:
        NotFoundError: If the provider does not exist.
    """
    if idp_crud.set_icon_uploaded(idp_id, False, db) is None:
        raise core_exceptions.NotFoundError("Identity provider not found")
    _stage_icon_audit(idp_id, db)
    db.commit()
    delete_blob(idp_id, storage)
    logger.info("Identity provider icon deleted", extra=core_logger.context(idp_id=idp_id))


def delete_blob(idp_id: int, storage: platform_providers.StorageProvider) -> None:
    """Delete an icon blob, logging a storage outage instead of failing: the flag decides whether it is served.

    A blob left behind is removed by the next upload over it or by the icon sweep.

    Args:
        idp_id: The provider the icon belongs to.
        storage: The platform storage provider.
    """
    try:
        storage.delete(idp_constants.ICON_STORAGE_AREA, _storage_key(idp_id))
    except platform_providers.StorageBackendUnavailableError as err:
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


def sweep_unreferenced_icons(storage: platform_providers.StorageProvider) -> int:
    """Delete icon blobs no provider names any more.

    The reconciliation net of the icon area: it removes what a failed best-effort delete left after a provider
    or its icon was removed, and an upload that lost a race with the provider's deletion.

    Args:
        storage: The platform storage provider.

    Returns:
        The number of blobs deleted.
    """
    removed = core_blob_sweep.sweep_unreferenced_blobs(storage, idp_constants.ICON_STORAGE_AREA, _referenced_icon_keys)
    if removed:
        logger.info("Removed identity provider icons no provider names", extra=core_logger.context(removed=removed))
    return removed


def _referenced_icon_keys(keys: list[str], db: Session) -> set[str]:
    """Tell which of the given icon-area keys must be kept.

    A key is ``{idp_id}``. It is kept while that provider exists and has an uploaded icon. A key that is not
    a provider id is not this area's to judge and is kept too.

    Args:
        keys: Keys found in the icon area.
        db: Database session.

    Returns:
        The keys to keep.
    """
    owners = {key: int(key) if key.isascii() and key.isdecimal() else None for key in keys}
    with_icon = idp_crud.get_ids_with_icon(sorted({owner for owner in owners.values() if owner is not None}), db)
    return {key for key, owner in owners.items() if owner is None or owner in with_icon}


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
