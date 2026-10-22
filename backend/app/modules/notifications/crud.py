"""CRUD operations for notifications."""

from datetime import datetime

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema
import modules.notifications.serializers as notifications_serializers

logger = core_logger.get_logger(__name__)

#: The unique constraint on ``(source_event_id, user_id, type)``.
_UNIQUE_EVENT_CONSTRAINT = "uq_notifications_source_event_user_type"


def get_user_notification_by_id(
    notification_id: int,
    user_id: int,
    db: Session,
) -> notifications_schema.NotificationRead | None:
    """Retrieve a notification by ID for a user.

    Args:
        notification_id: The notification ID.
        user_id: The owning user ID.
        db: Database session.

    Returns:
        The notification if found, otherwise None.
    """
    stmt = select(notifications_models.Notification).where(
        notifications_models.Notification.user_id == user_id,
        notifications_models.Notification.id == notification_id,
    )
    db_notification = db.execute(stmt).scalars().first()
    return notifications_serializers.to_read_schema(db_notification) if db_notification else None


def get_user_notifications_count(
    user_id: int,
    db: Session,
) -> int:
    """Count notifications for a user.

    Args:
        user_id: The owning user ID.
        db: Database session.

    Returns:
        Number of notifications for the user.
    """
    stmt = (
        select(func.count())
        .select_from(notifications_models.Notification)
        .where(notifications_models.Notification.user_id == user_id)
    )
    return db.execute(stmt).scalar_one()


def get_user_notifications_with_pagination(
    user_id: int,
    db: Session,
    page_number: int = 1,
    num_records: int = 5,
) -> list[notifications_schema.NotificationRead]:
    """Retrieve paginated notifications for a user, newest first.

    Args:
        user_id: The owning user ID.
        db: Database session.
        page_number: Page number (default 1).
        num_records: Records per page (default 5).

    Returns:
        The notifications for the page.
    """
    stmt = (
        select(notifications_models.Notification)
        .where(notifications_models.Notification.user_id == user_id)
        .order_by(desc(notifications_models.Notification.created_at), desc(notifications_models.Notification.id))
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    db_notifications = db.execute(stmt).scalars().all()
    return [notifications_serializers.to_read_schema(n) for n in db_notifications]


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
    """
    stmt = select(notifications_models.Notification).where(
        notifications_models.Notification.source_event_id == source_event_id,
        notifications_models.Notification.user_id == user_id,
        notifications_models.Notification.type == notification_type,
    )
    db_notification = db.execute(stmt).scalars().first()
    return notifications_serializers.to_read_schema(db_notification) if db_notification else None


def create_notification(
    notification: notifications_schema.NotificationCreate,
    db: Session,
) -> notifications_schema.NotificationRead:
    """Stage a new notification record.

    Flushes without committing: the caller owns the transaction.

    Args:
        notification: The notification data to create.
        db: Database session.

    Returns:
        The staged notification.
    """
    new_notification = notifications_models.Notification(
        user_id=notification.user_id,
        type=notification.type,
        source_event_id=notification.source_event_id,
        options=notification.options,
    )
    db.add(new_notification)
    db.flush()
    db.refresh(new_notification)
    return notifications_serializers.to_read_schema(new_notification)


def create_notification_once(
    notification: notifications_schema.NotificationCreate,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, bool]:
    """Stage an event-driven notification at most once.

    The insert runs in a savepoint, so losing a race on the
    (source event, user, type) key leaves the session usable for the lookup of the
    winner without rolling back what the caller already staged.

    Args:
        notification: Notification carrying a stable source event ID.
        db: Database session.

    Returns:
        The notification and whether this call created it.

    Raises:
        NotFoundError: If the owning user no longer exists.
        ConflictError: If an unrelated database constraint fails.
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
        with db.begin_nested():
            return create_notification(notification, db), True
    except IntegrityError as err:
        constraint = core_database.violated_constraint(err)
        if constraint is not None and constraint != _UNIQUE_EVENT_CONSTRAINT:
            raise core_exceptions.NotFoundError("User not found") from err
        existing = get_notification_by_source_event(
            notification.source_event_id,
            notification.user_id,
            notification.type,
            db,
        )
        if existing is None:
            raise core_exceptions.ConflictError("Notification conflicts with an existing record") from err
        logger.warning(
            "Recovered concurrent duplicate notification delivery",
            extra=core_logger.context(
                source_event_id=notification.source_event_id,
                user_id=notification.user_id,
                notification_type=notification.type,
            ),
        )
        return existing, False


def mark_notification_as_read(
    notification_id: int,
    user_id: int,
    db: Session,
) -> notifications_schema.NotificationRead | None:
    """Stage marking a notification as read for a user.

    Args:
        notification_id: The notification ID.
        user_id: The owning user ID.
        db: Database session.

    Returns:
        The updated notification, or None if not found.
    """
    stmt = select(notifications_models.Notification).where(
        notifications_models.Notification.user_id == user_id,
        notifications_models.Notification.id == notification_id,
    )
    notification = db.execute(stmt).scalars().first()
    if notification is None:
        return None
    notification.read = True
    db.flush()
    db.refresh(notification)
    return notifications_serializers.to_read_schema(notification)


def mark_all_notifications_as_read(
    user_id: int,
    db: Session,
) -> None:
    """Stage marking every unread notification of a user as read.

    Args:
        user_id: The owning user ID.
        db: Database session.
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
    db.flush()


def delete_user_reference_notifications(
    user_id: int,
    notification_type: int,
    referenced_user_id: int,
    db: Session,
) -> int:
    """Stage deleting a user's notifications of one type that name another user.

    Args:
        user_id: The user who owns the notifications.
        notification_type: The notification type to delete.
        referenced_user_id: The user named in the notification options.
        db: Database session.

    Returns:
        Number of notifications staged for deletion.
    """
    result = db.execute(
        delete(notifications_models.Notification).where(
            notifications_models.Notification.user_id == user_id,
            notifications_models.Notification.type == notification_type,
            notifications_models.Notification.options["user_id"].as_integer() == referenced_user_id,
        )
    )
    db.flush()
    return result.rowcount


def delete_read_notifications_before(cutoff: datetime, limit: int, db: Session) -> int:
    """Stage deleting up to ``limit`` read notifications created before ``cutoff``.

    Args:
        cutoff: Read notifications created before this moment are deleted.
        limit: Most rows to delete in this call.
        db: Database session.

    Returns:
        Number of notifications staged for deletion.
    """
    stale_ids = (
        select(notifications_models.Notification.id)
        .where(
            notifications_models.Notification.read,
            notifications_models.Notification.created_at < cutoff,
        )
        .limit(limit)
    )
    result = db.execute(
        delete(notifications_models.Notification).where(notifications_models.Notification.id.in_(stale_ids))
    )
    db.flush()
    return result.rowcount
