"""Notifications as the application stores them, for tests on the real database."""

import uuid

from sqlalchemy.orm import Session

import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
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
