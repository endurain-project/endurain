"""Utility functions for notification creation."""

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.schema as notifications_schema
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users.utils as users_utils
import modules.websocket.manager as websocket_manager
import modules.websocket.utils as websocket_utils
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


def _create_notification(
    notification_data: notifications_schema.NotificationCreate,
    db: Session | None = None,
) -> notifications_schema.NotificationRead:
    """
    Persist a notification using the blocking database session.

    Isolates all synchronous SQLAlchemy work so it can be dispatched to a
    worker thread and never run on the event loop. When ``db`` is None a
    dedicated session is opened and closed here, keeping the full database
    lifecycle off the event loop as well.

    Args:
        notification_data: The notification to create.
        db: An existing session to reuse, or None to open a dedicated one.

    Returns:
        The created NotificationRead schema.
    """
    if db is not None:
        return notifications_crud.create_notification(notification_data, db)
    with SessionLocal() as owned_db:
        return notifications_crud.create_notification(notification_data, owned_db)


async def _create_and_notify(
    notification_data: notifications_schema.NotificationCreate,
    ws_message: str,
    notify_user_id: int,
    ws_manager: websocket_manager.WebSocketManager,
    db: Session | None = None,
) -> notifications_schema.NotificationRead:
    """
    Create a notification and send a WebSocket message.

    The blocking database write is offloaded to a worker thread via
    ``run_in_threadpool`` so the event loop is never blocked; only the
    awaitable WebSocket push runs on the loop.

    Args:
        notification_data: The notification to create.
        ws_message: WebSocket message type string.
        notify_user_id: User to notify via WebSocket.
        ws_manager: WebSocket manager instance.
        db: Existing session to reuse, or None to open a dedicated one.

    Returns:
        The created NotificationRead schema.
    """
    notification = await run_in_threadpool(_create_notification, notification_data, db)
    json_data = {
        "message": ws_message,
        "notification_id": notification.id,
    }
    await websocket_utils.notify_frontend(notify_user_id, ws_manager, json_data)
    return notification


def create_activity_created_notification(
    user_id: int,
    activity_id: int,
    duplicate_start_time: bool,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str]:
    """Create the notification row for a newly stored activity (synchronous).

    For the ``activity.created`` subscriber: it only writes the row (the record) and
    returns it together with the websocket message type, leaving the best-effort
    websocket push to the caller (dispatched onto the main loop via the async
    bridge). No websocket work happens here, so it is safe to run on a durable
    job worker thread or inline on the bus.

    Args:
        user_id: The user to notify (the activity owner).
        activity_id: The stored activity's ID.
        duplicate_start_time: Whether the activity was flagged as a duplicate
            start time (raises the duplicate variant instead of the new one).
        db: Database session used for the row write.

    Returns:
        Tuple of the created notification and the websocket message type string.
    """
    if duplicate_start_time:
        notification_type = notifications_constants.NotificationType.DUPLICATE_ACTIVITY
        ws_message = "NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION"
    else:
        notification_type = notifications_constants.NotificationType.NEW_ACTIVITY
        ws_message = "NEW_ACTIVITY_NOTIFICATION"

    notification = notifications_crud.create_notification(
        notifications_schema.NotificationCreate(
            user_id=user_id,
            type=notification_type,
            options={"activity_id": activity_id},
        ),
        db,
    )
    return notification, ws_message


def create_new_follower_request_notification(
    requester_user_id: int,
    target_user_id: int,
    source_event_id: str,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str, bool]:
    """Create the 'new follower request' notification row (synchronous).

    For the ``follower.requested`` subscriber: it only writes the row (the record)
    for the target user and returns it together with the websocket message type,
    leaving the best-effort websocket push to the caller (dispatched onto the main
    loop via the async bridge). No websocket work happens here, so it is safe to
    run inline on the bus consumer thread.

    Args:
        requester_user_id: The user who requested to follow (named in the
            notification options).
        target_user_id: The user to notify (owns the notification row).
        source_event_id: Stable durable event identifier.
        db: Database session used for the row write.

    Returns:
        The notification, websocket message type, and whether it was created.

    Raises:
        HTTPException: 404 if the requesting user no longer exists.
    """
    user = users_crud.get_user_by_id(requester_user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
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
    return notification, "NEW_FOLLOWER_REQUEST_NOTIFICATION", created


def create_accepted_follower_request_notification(
    accepter_user_id: int,
    requester_user_id: int,
    source_event_id: str,
    db: Session,
) -> tuple[notifications_schema.NotificationRead, str, bool]:
    """Create the 'follow request accepted' notification row (synchronous).

    For the ``follower.accepted`` subscriber: it only writes the row (the record)
    for the original requester and returns it with the websocket message type,
    leaving the best-effort websocket push to the caller.

    Args:
        accepter_user_id: The user who accepted the request (named in the
            notification options).
        requester_user_id: The original requester to notify (owns the
            notification row).
        source_event_id: Stable durable event identifier.
        db: Database session used for the row write.

    Returns:
        The notification, websocket message type, and whether it was created.

    Raises:
        HTTPException: 404 if the accepting user no longer exists.
    """
    user = users_crud.get_user_by_id(accepter_user_id, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
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
    return notification, "NEW_FOLLOWER_REQUEST_ACCEPTED_NOTIFICATION", created


async def create_admin_new_sign_up_approval_request_notification(
    user: users_schema.UsersRead,
    websocket_manager: websocket_manager.WebSocketManager,
    db: Session,
) -> None:
    """
    Notify all admins of a new sign-up request.

    Args:
        user: The user requesting sign-up.
        websocket_manager: WebSocket manager instance.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If creation or notify fails.
    """
    try:
        admins = await run_in_threadpool(users_utils.get_admin_users_or_404, db)
        for admin in admins:
            await _create_and_notify(
                notifications_schema.NotificationCreate(
                    user_id=admin.id,
                    type=(notifications_constants.NotificationType.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST),
                    options={
                        "user_id": user.id,
                        "user_name": user.name,
                        "user_username": (user.username),
                    },
                ),
                "ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_NOTIFICATION",
                admin.id,
                websocket_manager,
                db,
            )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        logger.error(f"Error in create_admin_new_sign_up_approval_request_notification: {err}", exc_info=err)
        raise HTTPException(
            status_code=(status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail="Internal Server Error",
        ) from err


async def create_garmin_token_expired_notification(
    user_id: int,
    websocket_manager: websocket_manager.WebSocketManager,
) -> None:
    """
    Notify user that their Garmin Connect tokens expired and their account was unlinked.

    Args:
        user_id: The user ID to notify.
        websocket_manager: WebSocket manager instance.

    Returns:
        None.
    """
    try:
        await _create_and_notify(
            notifications_schema.NotificationCreate(
                user_id=user_id,
                type=(notifications_constants.NotificationType.GARMIN_TOKEN_EXPIRED),
                options={},
            ),
            "GARMIN_TOKEN_EXPIRED_NOTIFICATION",
            user_id,
            websocket_manager,
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        logger.error(f"Error in create_garmin_token_expired_notification: {err}", exc_info=err)
        raise HTTPException(
            status_code=(status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail="Internal Server Error",
        ) from err
