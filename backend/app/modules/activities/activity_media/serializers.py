"""ORM↔record transformation for activity media.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.models as activity_media_models


def to_read_schema(
    orm_media: activity_media_models.ActivityMedia,
) -> activity_media_contracts.ActivityMediaRecord:
    """Convert an ORM ``ActivityMedia`` row to its record.

    Args:
        orm_media: The ORM row to convert.

    Returns:
        The media record.
    """
    return activity_media_contracts.ActivityMediaRecord.model_validate(orm_media)
