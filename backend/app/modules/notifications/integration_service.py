"""The notifications surface consumed by other modules.

Notifications are raised *about* things that happen elsewhere, so the producers
that are not events are other modules. Each gets one named operation here.

Every operation is synchronous and **stages** the notification rows: the caller
owns the transaction, commits, and then pushes the live hint with
:func:`push_notification`. Nothing here touches the connection registry, so these
are safe to run where there is no event loop.
"""

from sqlalchemy.orm import Session

import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.schema as notifications_schema
import modules.websocket.integration_service as websocket_integration


def push_notification(user_id: int, notification: notifications_schema.NotificationRead, ws_message: str) -> None:
    """Tell a user's browser that a committed notification awaits.

    Args:
        user_id: The user who owns the notification.
        notification: The notification, already committed.
        ws_message: The websocket message type returned when it was staged or recorded.
    """
    websocket_integration.push_to_user(user_id, {"message": ws_message, "notification_id": notification.id})


def create_garmin_token_expired_notification(
    user_id: int,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str]:
    """Stage the notification that a Garmin Connect account was unlinked.

    Args:
        user_id: The user whose account was unlinked.
        db: Database session.

    Returns:
        The staged notification and the websocket message type the caller should
        push once it has committed.
    """
    notification = notifications_crud.create_notification(
        notifications_schema.NotificationCreate(
            user_id=user_id,
            type=notifications_constants.NotificationType.GARMIN_TOKEN_EXPIRED,
            options={},
        ),
        db,
    )
    return notification, notifications_constants.GARMIN_UNLINKED_WS_MESSAGE


def create_strava_token_expired_notification(
    user_id: int,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str]:
    """Stage the notification that a Strava account was unlinked.

    Args:
        user_id: The user whose account was unlinked.
        db: Database session.

    Returns:
        The staged notification and the websocket message type the caller should
        push once it has committed.
    """
    notification = notifications_crud.create_notification(
        notifications_schema.NotificationCreate(
            user_id=user_id,
            type=notifications_constants.NotificationType.STRAVA_TOKEN_EXPIRED,
            options={},
        ),
        db,
    )
    return notification, notifications_constants.STRAVA_UNLINKED_WS_MESSAGE


def delete_notifications_naming_user(user_id: int, db: Session) -> None:
    """Stage deleting the notifications, whoever owns them, that name a user being erased.

    Args:
        user_id: The user whose name and username the notifications carry.
        db: Database session.
    """
    notifications_crud.delete_notifications_naming_user(user_id, db)
