"""The notifications surface consumed by other modules.

Notifications are raised *about* things that happen elsewhere, so almost every
producer is another module. Each gets one named operation here rather than
reaching into ``utils`` — a grab-bag that also holds the module's own routes'
helpers and its websocket plumbing.

Every operation is synchronous and writes only the notification **row**. The
live websocket push is the caller's concern (dispatched onto the main loop), so
these are safe to run on a durable-job worker thread where there is no loop and
no connection registry.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.notifications.schema as notifications_schema
import modules.notifications.utils as notifications_utils

logger = core_logger.get_logger(__name__)


def create_activity_created_notification(
    user_id: int,
    activity_id: int,
    duplicate_start_time: bool,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str]:
    """
    Record the notification for a newly stored activity.

    Args:
        user_id: The owner to notify.
        activity_id: The stored activity.
        duplicate_start_time: Whether the activity duplicates an existing
            activity's start time, which selects the duplicate variant.
        db: Database session.

    Returns:
        The created notification row and the websocket message type the caller
        should push.

    Raises:
        None.
    """
    return notifications_utils.create_activity_created_notification(
        user_id,
        activity_id,
        duplicate_start_time,
        db,
    )


def create_follow_request_notification(
    requester_user_id: int,
    target_user_id: int,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str]:
    """
    Record the notification for a new follow request.

    Args:
        requester_user_id: The user who asked to follow, named in the notification.
        target_user_id: The user to notify, who owns the notification row.
        db: Database session.

    Returns:
        The created notification row and the websocket message type the caller
        should push.

    Raises:
        HTTPException: 404 when the requesting user no longer exists.
    """
    return notifications_utils.create_new_follower_request_notification(
        requester_user_id,
        target_user_id,
        db,
    )


def create_follow_accepted_notification(
    accepter_user_id: int,
    requester_user_id: int,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str]:
    """
    Record the notification for an accepted follow request.

    Args:
        accepter_user_id: The user who accepted, named in the notification.
        requester_user_id: The original requester to notify, who owns the row.
        db: Database session.

    Returns:
        The created notification row and the websocket message type the caller
        should push.

    Raises:
        HTTPException: 404 when the accepting user no longer exists.
    """
    return notifications_utils.create_accepted_follower_request_notification(
        accepter_user_id,
        requester_user_id,
        db,
    )
