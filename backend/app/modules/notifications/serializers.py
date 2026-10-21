"""ORM↔schema transformation for notifications.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema


def to_read_schema(notification: notifications_models.Notification) -> notifications_schema.NotificationRead:
    """Convert a Notification ORM row into its serialized DTO.

    Args:
        notification: The ORM row to convert.

    Returns:
        The notification DTO.

    Raises:
        ValidationError: If the row does not satisfy the DTO.
    """
    return notifications_schema.NotificationRead.model_validate(notification)
