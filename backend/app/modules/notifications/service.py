"""Application logic for notifications.

The user-facing reads and the mark-as-read writes behind the router, and the
creation of notifications in reaction to activity and follower events. Every
write commits here; the live websocket push is the caller's concern, so these
are safe to run on a durable-job worker thread where there is no event loop.

What other modules may consume lives in :mod:`modules.notifications.integration_service`.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.auth.identity_providers.integration_service as idp_integration
import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.schema as notifications_schema
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def user_reference_options(user: users_schema.UsersRead) -> dict[str, object]:
    """Build the notification options that name another user.

    Args:
        user: The user the notification refers to.

    Returns:
        The options carrying the user's ID, name and username.
    """
    return {"user_id": user.id, "user_name": user.name, "user_username": user.username}


def count_notifications(user_id: int, db: Session) -> int:
    """Count the user's notifications.

    Args:
        user_id: The owning user.
        db: Database session.

    Returns:
        Number of notifications for the user.
    """
    return notifications_crud.get_user_notifications_count(user_id, db)


def get_notification(notification_id: int, user_id: int, db: Session) -> notifications_schema.NotificationRead:
    """Return one of the user's notifications.

    Args:
        notification_id: The notification to fetch.
        user_id: The owning user.
        db: Database session.

    Returns:
        The notification.

    Raises:
        NotFoundError: When the user has no such notification.
    """
    notification = notifications_crud.get_user_notification_by_id(notification_id, user_id, db)
    if notification is None:
        raise core_exceptions.NotFoundError("Notification not found")
    return notification


def list_notifications(
    user_id: int,
    db: Session,
    *,
    page_number: int,
    num_records: int,
    unread_only: bool = False,
) -> core_pagination.Page[notifications_schema.NotificationRead]:
    """Return one page of the user's notifications, newest first.

    Args:
        user_id: The owning user.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.
        unread_only: Keep only the notifications that have not been read; the
            total follows the same filter.

    Returns:
        The page envelope with the user's total.
    """
    items = notifications_crud.get_user_notifications_with_pagination(
        user_id, db, page_number, num_records, unread_only=unread_only
    )
    total = notifications_crud.get_user_notifications_count(user_id, db, unread_only=unread_only)
    return core_pagination.Page.build(items, total, page_number, num_records)


def mark_notification_as_read(notification_id: int, user_id: int, db: Session) -> None:
    """Mark one of the user's notifications as read.

    Args:
        notification_id: The notification to mark.
        user_id: The owning user.
        db: Database session.

    Raises:
        NotFoundError: When the user has no such notification.
    """
    if notifications_crud.mark_notification_as_read(notification_id, user_id, db) is None:
        raise core_exceptions.NotFoundError("Notification not found")
    db.commit()
    logger.info(
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
    logger.info("Marked all notifications as read", extra=core_logger.context(user_id=user_id))


def delete_read_notifications(db: Session) -> int:
    """Delete read notifications past the retention period, one batch per commit.

    Args:
        db: Database session.

    Returns:
        Number of notifications deleted; zero when the retention setting disables pruning.
    """
    retention_days = server_settings_integration.get_read_notification_retention_days(db)
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    total = core_database.delete_in_batches(
        lambda limit: notifications_crud.delete_read_notifications_before(cutoff, limit, db), db
    )
    logger.info("Purged read notifications", extra=core_logger.context(deleted=total))
    return total


def _record_event_notification(
    user_id: int,
    notification_type: notifications_constants.NotificationType,
    ws_message: str,
    options: dict[str, object],
    source_event_id: str,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str, bool]:
    """Record an event-driven notification once and commit it.

    Delivery is at-least-once, so the row is keyed by the source event: a
    redelivered event finds its notification instead of creating a second one.

    Args:
        user_id: The user who owns the notification.
        notification_type: The notification type to record.
        ws_message: The websocket message type the caller should push.
        options: The notification options.
        source_event_id: Stable durable event identifier.
        db: Database session.

    Returns:
        The notification, the websocket message type the caller should push, and
        whether this call created it (False for a redelivered event).
    """
    notification, created = notifications_crud.create_notification_once(
        notifications_schema.NotificationCreate(
            user_id=user_id,
            type=notification_type,
            source_event_id=source_event_id,
            options=options,
        ),
        db,
    )
    db.commit()
    logger.debug(
        "Recorded notification",
        extra=core_logger.context(
            user_id=user_id, notification_id=notification.id, notification_type=notification_type, created=created
        ),
    )
    return notification, ws_message, created


def create_activity_created_notification(
    user_id: int,
    activity_id: int,
    duplicate_start_time: bool,
    source_event_id: str,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str, bool]:
    """Record the notification for a newly stored activity.

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
    return _record_event_notification(
        user_id, notification_type, ws_message, {"activity_id": activity_id}, source_event_id, db
    )


def _create_user_reference_notification(
    named_user_id: int,
    owner_user_id: int,
    notification_type: notifications_constants.NotificationType,
    ws_message: str,
    source_event_id: str,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str, bool]:
    """Record a notification that names another user.

    Args:
        named_user_id: The user the notification refers to.
        owner_user_id: The user who owns the notification row.
        notification_type: The notification type to record.
        ws_message: The websocket message type the caller should push.
        source_event_id: Stable durable event identifier.
        db: Database session.

    Returns:
        The notification, the websocket message type to push, and whether this call created it.

    Raises:
        NotFoundError: When the named user no longer exists.
    """
    user = users_integration.get_user(named_user_id, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")
    return _record_event_notification(
        owner_user_id, notification_type, ws_message, user_reference_options(user), source_event_id, db
    )


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
    return _create_user_reference_notification(
        requester_user_id,
        target_user_id,
        notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST,
        notifications_constants.NEW_FOLLOWER_REQUEST_WS_MESSAGE,
        source_event_id,
        db,
    )


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
    return _create_user_reference_notification(
        accepter_user_id,
        requester_user_id,
        notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST_ACCEPTED,
        notifications_constants.NEW_FOLLOWER_REQUEST_ACCEPTED_WS_MESSAGE,
        source_event_id,
        db,
    )


def remove_follow_request_notifications(requester_user_id: int, target_user_id: int, db: Session) -> bool:
    """Delete the "wants to follow you" notifications a removed follow request left behind.

    Args:
        requester_user_id: The user whose request was removed, named in the notifications.
        target_user_id: The user who owns the notifications.
        db: Database session.

    Returns:
        True when at least one notification was deleted.
    """
    deleted = notifications_crud.delete_user_reference_notifications(
        target_user_id,
        notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST,
        requester_user_id,
        db,
    )
    db.commit()
    logger.debug(
        "Removed follow-request notifications",
        extra=core_logger.context(requester_user_id=requester_user_id, target_user_id=target_user_id, deleted=deleted),
    )
    return deleted > 0


def create_idp_linked_notification(
    user_id: int,
    idp_id: int,
    source_event_id: str,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str, bool]:
    """Record the notification that a sign-in provider was linked to the account.

    The provider's name is included when it still exists; a provider deleted since
    the event leaves the notification without one.

    Args:
        user_id: The user whose account gained the link, who owns the notification row.
        idp_id: The linked identity provider.
        source_event_id: Stable durable event identifier.
        db: Database session.

    Returns:
        The notification, the websocket message type the caller should push, and
        whether this call created it.

    Raises:
        NotFoundError: When the user no longer exists.
    """
    if users_integration.get_user(user_id, db) is None:
        raise core_exceptions.NotFoundError("User not found")
    idp = idp_integration.get_identity_provider(idp_id, db)
    return _record_event_notification(
        user_id,
        notifications_constants.NotificationType.IDP_LINKED,
        notifications_constants.IDP_LINKED_WS_MESSAGE,
        {"idp_id": idp_id, "idp_name": idp.name if idp is not None else None},
        source_event_id,
        db,
    )
