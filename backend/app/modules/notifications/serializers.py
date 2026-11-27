"""ORM↔schema transformation for notifications.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.notifications.constants as notifications_constants
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema


def to_read_schema(notification: notifications_models.Notification) -> notifications_schema.NotificationRead:
    """Convert a Notification ORM row into its serialized DTO.

    Args:
        notification: The ORM row to convert.

    Returns:
        The notification DTO, whose options are the ones its type stores.

    Raises:
        ValidationError: If the row does not satisfy the DTO of its type.
        ValueError: If the stored type is not a notification type.
    """
    return notifications_schema.NOTIFICATION_READ_ADAPTER.validate_python(
        {
            "id": notification.id,
            "type": notifications_constants.NotificationType.from_stored(notification.type),
            "user_id": notification.user_id,
            "read": notification.read,
            "created_at": notification.created_at,
            "options": notification.options if notification.options is not None else {},
        }
    )
