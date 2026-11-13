"""CRUD operations for notifications."""

import uuid
from datetime import datetime

from sqlalchemy import delete, desc, func, literal, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.notifications.constants as notifications_constants
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema
import modules.notifications.serializers as notifications_serializers

logger = core_logger.get_logger(__name__)

#: The unique constraint on ``(source_event_id, user_id, type)``.
_UNIQUE_EVENT_CONSTRAINT = "uq_notifications_source_event_user_type"


def get_user_notification_by_id(
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
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


def count_user_unread_notifications(user_id: uuid.UUID, db: Session) -> int:
    """Count the notifications of a user that have not been read.

    Args:
        user_id: The owning user ID.
        db: Database session.

    Returns:
        Number of unread notifications for the user.
    """
    stmt = (
        select(func.count())
        .select_from(notifications_models.Notification)
        .where(
            notifications_models.Notification.user_id == user_id,
            notifications_models.Notification.read.is_(False),
        )
    )
    return db.execute(stmt).scalar_one()


def get_user_notifications_after(
    user_id: uuid.UUID,
    after: tuple[datetime, uuid.UUID] | None,
    num_records: int,
    db: Session,
    unread_only: bool = False,
) -> list[notifications_schema.NotificationRead]:
    """Get the next keyset slice of a user's notifications, newest first.

    Ordered by ``(created_at DESC, id DESC)``. ``id`` is part of the key because ``created_at`` is not
    unique, so two notifications sharing one would otherwise straddle the boundary.

    Args:
        user_id: The owning user ID.
        after: The ``(created_at, id)`` position to resume strictly after, or ``None`` for the first slice.
        num_records: Maximum records to return.
        db: Database session.
        unread_only: Keep only the notifications that have not been read.

    Returns:
        The slice, newest first (empty when there is nothing more).
    """
    notification = notifications_models.Notification
    stmt = select(notification).where(notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(notification.read.is_(False))
    if after is not None:
        last_created_at, last_id = after
        # Row-value comparison: strictly older, or the same time with a lower id.
        stmt = stmt.where(
            tuple_(notification.created_at, notification.id) < tuple_(literal(last_created_at), literal(last_id))
        )
    stmt = stmt.order_by(desc(notification.created_at), desc(notification.id)).limit(num_records)
    return [notifications_serializers.to_read_schema(n) for n in db.execute(stmt).scalars().all()]


def get_notification_by_source_event(
    source_event_id: str,
    user_id: uuid.UUID,
    notification_type: notifications_constants.NotificationType,
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
        notifications_models.Notification.type == notification_type.stored,
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
        type=notification.type.stored,
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
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
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


def mark_notifications_as_read(
    notification_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    db: Session,
) -> None:
    """Stage marking some of a user's notifications as read; ids that are not the user's are skipped.

    Args:
        notification_ids: The notifications to mark.
        user_id: The owning user ID.
        db: Database session.
    """
    stmt = (
        update(notifications_models.Notification)
        .where(
            notifications_models.Notification.user_id == user_id,
            notifications_models.Notification.id.in_(notification_ids),
        )
        .values(read=True)
    )
    db.execute(stmt)
    db.flush()


def delete_user_notification(
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session,
) -> bool:
    """Stage deleting one of a user's notifications.

    Args:
        notification_id: The notification ID.
        user_id: The owning user ID.
        db: Database session.

    Returns:
        True when the notification was deleted, False when the user has no such notification.
    """
    stmt = (
        delete(notifications_models.Notification)
        .where(
            notifications_models.Notification.user_id == user_id,
            notifications_models.Notification.id == notification_id,
        )
        .returning(notifications_models.Notification.id)
    )
    deleted = db.execute(stmt).scalar_one_or_none() is not None
    db.flush()
    return deleted


def mark_all_notifications_as_read(
    user_id: uuid.UUID,
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
    user_id: uuid.UUID,
    notification_type: notifications_constants.NotificationType,
    referenced_user_id: uuid.UUID,
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
    matched = core_database.rowcount(
        db,
        delete(notifications_models.Notification).where(
            notifications_models.Notification.user_id == user_id,
            notifications_models.Notification.type == notification_type.stored,
            notifications_models.Notification.options["user_id"].as_string() == str(referenced_user_id),
        ),
    )
    db.flush()
    return matched


def delete_notifications_naming_user(referenced_user_id: uuid.UUID, db: Session) -> int:
    """Stage deleting every notification, whoever owns it, whose options name a user.

    Args:
        referenced_user_id: The user named in the notification options.
        db: Database session.

    Returns:
        Number of notifications staged for deletion.
    """
    matched = core_database.rowcount(
        db,
        delete(notifications_models.Notification).where(
            notifications_models.Notification.options["user_id"].as_string() == str(referenced_user_id)
        ),
    )
    db.flush()
    return matched


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
    matched = core_database.rowcount(
        db, delete(notifications_models.Notification).where(notifications_models.Notification.id.in_(stale_ids))
    )
    db.flush()
    return matched
