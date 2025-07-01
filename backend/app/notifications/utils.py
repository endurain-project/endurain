import notifications.schema as notifications_schema


def serialize_notification(notification: notifications_schema.Notification):
    # Serialize the notification object
    notification.created_at = notification.created_at.strftime("%Y-%m-%d")

    # Return the serialized notification object
    return notification
