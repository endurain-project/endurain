"""CRUD operations for notifications."""

from typing import overload

from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema

# Private internal helpers


@overload
def _transform_notifications(
    notifications: notifications_models.Notification,
) -> notifications_schema.NotificationRead: ...


@overload
def _transform_notifications(
    notifications: list[notifications_models.Notification],
) -> list[notifications_schema.NotificationRead]: ...


def _transform_notifications(
    notifications: notifications_models.Notification | list[notifications_models.Notification],
) -> notifications_schema.NotificationRead | list[notifications_schema.NotificationRead]:
    """
    Transform a notification or list of notifications to a Pydantic schema.

      Args:
        notifications: The notification ORM instance or list of instances.

      Returns:
        The notification(s) as a schema.
    """
    if isinstance(notifications, list):
        return [notifications_schema.NotificationRead.model_validate(n) for n in notifications]
    return notifications_schema.NotificationRead.model_validate(notifications)


# Public CRUD functions


@core_decorators.handle_db_errors
def get_user_notification_by_id(
    notification_id: int,
    user_id: int,
    db: Session,
) -> notifications_schema.NotificationRead | None:
    """
    Retrieve a notification by ID for a user.

    Args:
        notification_id: The notification ID.
        user_id: The owning user ID.
        db: Database session.

    Returns:
        Notification model if found, otherwise None.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(notifications_models.Notification).where(
        notifications_models.Notification.user_id == user_id,
        notifications_models.Notification.id == notification_id,
    )
    db_notifications = db.execute(stmt).scalars().first()

    return _transform_notifications(db_notifications) if db_notifications else None


@core_decorators.handle_db_errors
def get_user_notifications_count(
    user_id: int,
    db: Session,
) -> int:
    """
    Count notifications for a user.

    Args:
        user_id: The owning user ID.
        db: Database session.

    Returns:
        Number of notifications for the user.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = (
        select(func.count())
        .select_from(notifications_models.Notification)
        .where(notifications_models.Notification.user_id == user_id)
    )
    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_user_notifications_with_pagination(
    user_id: int,
    db: Session,
    page_number: int = 1,
    num_records: int = 5,
) -> list[notifications_schema.NotificationRead]:
    """
    Retrieve paginated notifications for a user.

    Args:
        user_id: The owning user ID.
        db: Database session.
        page_number: Page number (default 1).
        num_records: Records per page (default 5).

    Returns:
        List of NotificationRead schemas for the page.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = (
        select(notifications_models.Notification)
        .where(notifications_models.Notification.user_id == user_id)
        .order_by(desc(notifications_models.Notification.created_at))
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    db_notifications = db.execute(stmt).scalars().all()
    return _transform_notifications(list(db_notifications))


@core_decorators.handle_db_errors
def create_notification(
    notification: notifications_schema.NotificationCreate,
    db: Session,
) -> notifications_schema.NotificationRead:
    """
    Create a new notification record.

    Args:
        notification: The notification data to create.
        db: Database session.

    Returns:
        The newly created NotificationRead schema.

    Raises:
        HTTPException: If a database error occurs.
    """
    new_notification = notifications_models.Notification(
        user_id=notification.user_id,
        type=notification.type,
        options=notification.options,
        read=False,
        created_at=func.now(),
    )
    db.add(new_notification)
    db.commit()
    db.refresh(new_notification)
    return _transform_notifications(new_notification)


@core_decorators.handle_db_errors
def mark_notification_as_read(
    notification_id: int,
    user_id: int,
    db: Session,
) -> notifications_schema.NotificationRead | None:
    """
    Mark a notification as read for a user.

    Args:
        notification_id: The notification ID.
        user_id: The owning user ID.
        db: Database session.

    Returns:
        Updated NotificationRead schema, or None if not found.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(notifications_models.Notification).where(
        notifications_models.Notification.user_id == user_id,
        notifications_models.Notification.id == notification_id,
    )
    notification = db.execute(stmt).scalars().first()
    if notification is None:
        return None
    notification.read = True
    db.commit()
    db.refresh(notification)
    return _transform_notifications(notification)


@core_decorators.handle_db_errors
def mark_all_notifications_as_read(
    user_id: int,
    db: Session,
) -> None:
    """
    Mark all unread notifications as read for a user.

    Args:
        user_id: The owning user ID.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = (
        update(notifications_models.Notification)
        .where(
            notifications_models.Notification.user_id == user_id,
            notifications_models.Notification.read.is_(False),
        )
        .values(read=True)
    )
    db.execute(stmt)
    db.commit()
