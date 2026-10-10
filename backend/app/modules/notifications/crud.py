"""CRUD operations for notifications."""

from typing import overload

from sqlalchemy import desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema

logger = core_logger.get_logger(__name__)

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
def get_notification_by_source_event(
    source_event_id: str,
    user_id: int,
    notification_type: int | None,
    db: Session,
) -> notifications_schema.NotificationRead | None:
    """Retrieve a notification created for a durable event.

    Args:
        source_event_id: Stable durable event identifier.
        user_id: User who owns the notification.
        notification_type: Notification type produced by the handler.
        db: Database session.

    Returns:
        The existing notification, or None when the event has not been handled.

    Raises:
        ProcessingError: If the database query fails.
    """
    stmt = select(notifications_models.Notification).where(
        notifications_models.Notification.source_event_id == source_event_id,
        notifications_models.Notification.user_id == user_id,
        notifications_models.Notification.type == notification_type,
    )
    db_notification = db.execute(stmt).scalars().first()
    return _transform_notifications(db_notification) if db_notification else None


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
        source_event_id=notification.source_event_id,
        options=notification.options,
        read=False,
        created_at=func.now(),
    )
    db.add(new_notification)
    db.commit()
    db.refresh(new_notification)
    return _transform_notifications(new_notification)


@core_decorators.handle_db_errors
def create_notification_once(
    notification: notifications_schema.NotificationCreate,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, bool]:
    """Create an event-driven notification at most once.

    Args:
        notification: Notification carrying a stable source event ID.
        db: Database session.

    Returns:
        The notification and whether this call created it.

    Raises:
        IntegrityError: If an unrelated database constraint fails.
        ProcessingError: If a database operation fails.
    """
    if notification.source_event_id is None:
        return create_notification(notification, db), True

    existing = get_notification_by_source_event(
        notification.source_event_id,
        notification.user_id,
        notification.type,
        db,
    )
    if existing is not None:
        return existing, False

    try:
        return create_notification(notification, db), True
    except IntegrityError:
        existing = get_notification_by_source_event(
            notification.source_event_id,
            notification.user_id,
            notification.type,
            db,
        )
        if existing is None:
            raise
        logger.warning(
            "Recovered concurrent duplicate notification delivery",
            extra=core_logger.context(
                source_event_id=notification.source_event_id,
                user_id=notification.user_id,
                notification_type=notification.type,
            ),
        )
        return existing, False


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
