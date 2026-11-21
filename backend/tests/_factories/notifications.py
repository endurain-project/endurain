"""Notifications as the application stores them, for tests on the real database."""

import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema


def make_notification(db: Session, user_id: uuid.UUID) -> notifications_schema.NotificationRead:
    """Stage an unread notification through the module's create function (flushed, not committed).

    The notification is of a type that carries no options.

    Args:
        db: Database session.
        user_id: The notification's recipient.

    Returns:
        The staged notification.
    """
    return notifications_crud.create_notification(
        notifications_schema.NotificationCreate(
            type=notifications_constants.NotificationType.GARMIN_TOKEN_EXPIRED, user_id=user_id
        ),
        db,
    )


def make_notification_of(
    db: Session,
    user_id: uuid.UUID,
    notification_type: notifications_constants.NotificationType,
    options: dict[str, object] | None = None,
    *,
    read: bool = False,
    created_at: datetime | None = None,
    source_event_id: str | None = None,
) -> notifications_schema.NotificationRead:
    """Stage a notification of any type through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The notification's recipient.
        notification_type: The notification's type.
        options: The options the type carries; none when omitted.
        read: Whether the notification has been read.
        created_at: When the notification was created; now when omitted.
        source_event_id: The durable event it answers, when it is event-driven.

    Returns:
        The staged notification, as stored.
    """
    created = notifications_crud.create_notification(
        notifications_schema.NotificationCreate(
            type=notification_type, user_id=user_id, options=options or {}, source_event_id=source_event_id
        ),
        db,
    )
    if read or created_at is not None:
        values: dict[str, object] = {"read": read}
        if created_at is not None:
            values["created_at"] = created_at
        db.execute(
            update(notifications_models.Notification)
            .where(notifications_models.Notification.id == created.id)
            .values(**values)
        )
        db.flush()
        stored = notifications_crud.get_user_notification_by_id(created.id, user_id, db)
        assert stored is not None
        return stored
    return created
