"""Public storage operations for retained activity source files."""

import infra.providers as platform_providers
import modules.activities.activity_file_storage.service as file_storage_service


def store_activity_file(
    activity_id: int,
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> str:
    """Store one activity's retained source file."""
    return file_storage_service.store_activity_file(activity_id, extension, data, storage)


def store_activity_file_for_ids(
    activity_ids: list[int],
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> None:
    """Store one retained source file for several parsed activities."""
    file_storage_service.store_activity_file_for_ids(activity_ids, extension, data, storage)


def get_activity_file(
    activity_id: int,
    storage: platform_providers.StorageProvider,
) -> tuple[str, bytes] | None:
    """Return an activity's retained source file when present."""
    return file_storage_service.get_activity_file(activity_id, storage)


def delete_activity_file(activity_id: int, storage: platform_providers.StorageProvider) -> None:
    """Delete every retained source-file key for an activity."""
    file_storage_service.delete_activity_file(activity_id, storage)
