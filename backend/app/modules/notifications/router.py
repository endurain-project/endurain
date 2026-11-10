"""Notification API route handlers."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Security, status

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.notifications.schema as notifications_schema
import modules.notifications.service as notifications_service

router = APIRouter()


@router.get(
    "/unread-count",
    response_model=notifications_schema.NotificationUnreadCount,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
)
def read_unread_notifications_count(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> notifications_schema.NotificationUnreadCount:
    """Return how many of the caller's notifications have not been read."""
    return notifications_schema.NotificationUnreadCount(
        count=notifications_service.count_unread_notifications(token_user_id, db)
    )


@router.get(
    "/{notification_id}",
    response_model=notifications_schema.NotificationRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
)
def read_notifications_by_id(
    notification_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> notifications_schema.NotificationRead:
    """Retrieve a notification by ID for the user.

    Args:
        notification_id: Unique ID of the notification.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        The notification.
    """
    return notifications_service.get_notification(notification_id, token_user_id, db)


@router.get(
    "",
    response_model=notifications_schema.NotificationPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
)
def read_notifications_user_pagination(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    cursor: Annotated[str | None, Query()] = None,
    num_records: Annotated[int | None, Query(ge=1, le=core_pagination.MAX_NUM_RECORDS)] = None,
    unread_only: Annotated[bool, Query()] = False,
) -> notifications_schema.NotificationPage:
    """List a keyset slice of the caller's notifications, newest first.

    Pass the `next_cursor` of a slice as `cursor` to get the following one; it is `null` on the last slice.
    `unread_only=true` keeps only the notifications that have not been read, and must stay the same across the
    slices of one walk.
    """
    return notifications_service.list_notifications(
        token_user_id,
        db,
        cursor=cursor,
        num_records=num_records or core_pagination.DEFAULT_NUM_RECORDS,
        unread_only=unread_only,
    )


@router.post(
    "/{notification_id}/read",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def mark_notification_as_read(
    request: Request,
    notification_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Mark a specific notification as read.

    Args:
        request: The incoming request, used by the rate limiter.
        notification_id: ID of the notification to mark as read.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        None.
    """
    notifications_service.mark_notification_as_read(notification_id, token_user_id, db)


@router.post(
    "/read",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def mark_notifications_as_read(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    body: notifications_schema.NotificationsMarkRead | None = None,
) -> None:
    """Mark notifications as read.

    With `{"ids": [...]}` (at most 100) only those are marked; an id that is not the caller's is skipped, so the
    answer does not reveal which ids exist. Without a body every unread notification of the caller is marked.
    """
    if body is None:
        notifications_service.mark_all_notifications_as_read(token_user_id, db)
    else:
        notifications_service.mark_notifications_as_read(body.ids, token_user_id, db)


@router.delete(
    "/{notification_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_notification(
    request: Request,
    notification_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Delete one of the caller's notifications. `404` when the caller has no such notification."""
    notifications_service.delete_notification(notification_id, token_user_id, db)
