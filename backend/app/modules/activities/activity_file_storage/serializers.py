"""ORM to contract transformation for retained activity files."""

import modules.activities.activity_file_storage.contracts as activity_file_storage_contracts
import modules.activities.activity_file_storage.models as activity_file_storage_models


def to_ref(row: activity_file_storage_models.ActivityFile) -> activity_file_storage_contracts.ActivityFileRef:
    """Describe a stored row as a file reference.

    Args:
        row: The ORM row.

    Returns:
        The reference.
    """
    return activity_file_storage_contracts.ActivityFileRef(
        file_id=row.id,
        storage_key=row.storage_key,
        extension=row.extension,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
    )
