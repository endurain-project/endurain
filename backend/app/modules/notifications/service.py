"""Application logic for notifications.

The user-facing reads and the mark-as-read writes behind the router, and the
creation of notifications in reaction to activity and follower events. Every
write commits here; the live websocket push is the caller's concern, so these
are safe to run on a durable-job worker thread where there is no event loop.

What other modules may consume lives in :mod:`modules.notifications.integration_service`.
"""

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.schema as notifications_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def count_notifications(user_id: int, db: Session) -> int:
    """Count the user's notifications.

    Args:
        user_id: The owning user.
        db: Database session.

    Returns:
        Number of notifications for the user.
    """
    return notifications_crud.get_user_notifications_count(user_id, db)


def get_notification(notification_id: int, user_id: int, db: Session) -> notifications_schema.NotificationRead | None:
    """Return one of the user's notifications.

    Args:
        notification_id: The notification to fetch.
        user_id: The owning user.
        db: Database session.

    Returns:
        The notification, or None when the user has no such notification.
    """
    return notifications_crud.get_user_notification_by_id(notification_id, user_id, db)


def list_notifications(
    user_id: int,
    db: Session,
    *,
    page_number: int,
    num_records: int,
) -> list[notifications_schema.NotificationRead]:
    """Return one page of the user's notifications, newest first.

    Args:
        user_id: The owning user.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The notifications for the page.
    """
    return notifications_crud.get_user_notifications_with_pagination(user_id, db, page_number, num_records)


def mark_notification_as_read(notification_id: int, user_id: int, db: Session) -> None:
    """Mark one of the user's notifications as read.

    A notification the user does not own is left alone and not reported.

    Args:
        notification_id: The notification to mark.
        user_id: The owning user.
        db: Database session.
    """
    notifications_crud.mark_notification_as_read(notification_id, user_id, db)
    db.commit()
    logger.debug(
        "Marked notification as read",
        extra=core_logger.context(notification_id=notification_id, user_id=user_id),
    )


def mark_all_notifications_as_read(user_id: int, db: Session) -> None:
    """Mark every unread notification of the user as read.

    Args:
        user_id: The owning user.
        db: Database session.
    """
    notifications_crud.mark_all_notifications_as_read(user_id, db)
    db.commit()
    logger.debug("Marked all notifications as read", extra=core_logger.context(user_id=user_id))


def create_activity_created_notification(
    user_id: int,
    activity_id: int,
    duplicate_start_time: bool,
    source_event_id: str,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str, bool]:
    """Record the notification for a newly stored activity.

    Delivery is at-least-once, so the row is keyed by the source event: a
    redelivered event finds its notification instead of creating a second one.

    Args:
        user_id: The owner to notify.
        activity_id: The stored activity.
        duplicate_start_time: Whether the activity duplicates an existing
            activity's start time, which selects the duplicate variant.
        source_event_id: Stable durable event identifier.
        db: Database session.

    Returns:
        The notification, the websocket message type the caller should push, and
        whether this call created it (False for a redelivered event).
    """
    if duplicate_start_time:
        notification_type = notifications_constants.NotificationType.DUPLICATE_ACTIVITY
        ws_message = notifications_constants.DUPLICATE_ACTIVITY_WS_MESSAGE
    else:
        notification_type = notifications_constants.NotificationType.NEW_ACTIVITY
        ws_message = notifications_constants.NEW_ACTIVITY_WS_MESSAGE

    notification, created = notifications_crud.create_notification_once(
        notifications_schema.NotificationCreate(
            user_id=user_id,
            type=notification_type,
            source_event_id=source_event_id,
            options={"activity_id": activity_id},
        ),
        db,
    )
    db.commit()
    logger.debug(
        "Recorded activity notification",
        extra=core_logger.context(
            activity_id=activity_id, user_id=user_id, notification_id=notification.id, created=created
        ),
    )
    return notification, ws_message, created


def create_follow_request_notification(
    requester_user_id: int,
    target_user_id: int,
    source_event_id: str,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str, bool]:
    """Record the notification for a new follow request.

    Args:
        requester_user_id: The user who asked to follow, named in the notification.
        target_user_id: The user to notify, who owns the notification row.
        source_event_id: Stable durable event identifier.
        db: Database session.

    Returns:
        The notification, the websocket message type the caller should push, and
        whether this call created it.

    Raises:
        NotFoundError: When the requesting user no longer exists.
    """
    user = users_integration.get_user(requester_user_id, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")
    notification, created = notifications_crud.create_notification_once(
        notifications_schema.NotificationCreate(
            user_id=target_user_id,
            type=notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST,
            source_event_id=source_event_id,
            options={
                "user_id": requester_user_id,
                "user_name": user.name,
                "user_username": user.username,
            },
        ),
        db,
    )
    db.commit()
    logger.debug(
        "Recorded follow-request notification",
        extra=core_logger.context(
            requester_user_id=requester_user_id,
            target_user_id=target_user_id,
            notification_id=notification.id,
            created=created,
        ),
    )
    return notification, notifications_constants.NEW_FOLLOWER_REQUEST_WS_MESSAGE, created


def create_follow_accepted_notification(
    accepter_user_id: int,
    requester_user_id: int,
    source_event_id: str,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str, bool]:
    """Record the notification for an accepted follow request.

    Args:
        accepter_user_id: The user who accepted, named in the notification.
        requester_user_id: The original requester to notify, who owns the row.
        source_event_id: Stable durable event identifier.
        db: Database session.

    Returns:
        The notification, the websocket message type the caller should push, and
        whether this call created it.

    Raises:
        NotFoundError: When the accepting user no longer exists.
    """
    user = users_integration.get_user(accepter_user_id, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")
    notification, created = notifications_crud.create_notification_once(
        notifications_schema.NotificationCreate(
            user_id=requester_user_id,
            type=notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST_ACCEPTED,
            source_event_id=source_event_id,
            options={
                "user_id": accepter_user_id,
                "user_name": user.name,
                "user_username": user.username,
            },
        ),
        db,
    )
    db.commit()
    logger.debug(
        "Recorded follow-accepted notification",
        extra=core_logger.context(
            accepter_user_id=accepter_user_id,
            requester_user_id=requester_user_id,
            notification_id=notification.id,
            created=created,
        ),
    )
    return notification, notifications_constants.NEW_FOLLOWER_REQUEST_ACCEPTED_WS_MESSAGE, created
