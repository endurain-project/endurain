"""Storage-backed file writers for the profile data export.

Adds the user's profile image to the export ZIP. It is read through the platform ``StorageProvider``,
so an export is complete whichever storage backend is configured.
"""

import os
import uuid
import zipfile

import jasil.providers as platform_providers

import core.logger as core_logger
import modules.users.users.constants as users_constants
import modules.users.users_profile.utils as users_profile_utils

logger = core_logger.get_logger(__name__)


def add_user_images_to_zip(
    zipf: zipfile.ZipFile,
    user_id: uuid.UUID,
    storage: platform_providers.StorageProvider,
    counts: dict[str, int],
    performance_config: users_profile_utils.BasePerformanceConfig,
) -> None:
    """Add the user's profile image to the ZIP archive.

    Read through the platform ``StorageProvider`` rather than by walking a
    local directory, so an export is complete regardless of which storage
    backend is configured. Keys are ``{user_id}{ext}``, so the caller's
    blobs are listed by their own prefix instead of scanning every stored
    image and filtering by filename.

    Args:
        zipf: ZipFile instance to write to.
        user_id: ID of the user whose profile image is exported.
        storage: The platform storage provider.
        counts: Exported item counts, updated as items are written.
        performance_config: Memory limits.
    """
    area = users_constants.USER_IMAGE_STORAGE_AREA

    try:
        keys = storage.list_keys(area, f"{user_id}.")
    except platform_providers.StorageBackendUnavailableError as err:
        logger.warning("Failed to list user images", exc_info=err, extra=core_logger.context(user_id=user_id))
        return

    for key in keys:
        try:
            data = storage.get(area, key)
        except platform_providers.StorageBackendUnavailableError as err:
            logger.warning("Could not read a user image; skipping it", exc_info=err, extra=core_logger.context(key=key))
            continue
        if data is None:
            logger.warning("User image blob not found", extra=core_logger.context(key=key))
            continue

        size = len(data)
        if size > 10 * 1024 * 1024:
            logger.warning("Large user image file", extra=core_logger.context(key=key, size_mb=size / (1024 * 1024)))
        if size > 5 * 1024 * 1024:
            users_profile_utils.check_memory_usage(
                f"before image {key}",
                performance_config.max_memory_mb,
                performance_config.enable_memory_monitoring,
            )

        zipf.writestr(os.path.join("user_images", key), data)
        counts["user_images"] += 1
