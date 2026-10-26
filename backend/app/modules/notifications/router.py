"""Notification API route handlers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security, status

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.notifications.schema as notifications_schema
import modules.notifications.service as notifications_service

router = APIRouter()


@router.get(
    "/number",
    response_model=int,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
)
def read_notifications_number(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> int:
    """Retrieve notification count for the user.

    Args:
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        Number of notifications for the user.
    """
    return notifications_service.count_notifications(token_user_id, db)


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
    response_model=core_pagination.Page[notifications_schema.NotificationRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
)
def read_notifications_user_pagination(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
    unread_only: Annotated[bool, Query()] = False,
) -> core_pagination.Page[notifications_schema.NotificationRead]:
    """Retrieve paginated notifications for the user.

    Args:
        token_user_id: ID of the user from the access token.
        db: Database session dependency.
        page: Resolved page number and size.
        unread_only: Keep only the notifications that have not been read. ``total`` follows the
            same filter, so ``unread_only=true&num_records=1`` is the unread count.

    Returns:
        The page of notifications with the user's total.
    """
    return notifications_service.list_notifications(
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        unread_only=unread_only,
    )


@router.put(
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


@router.put(
    "/read",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def mark_all_notifications_as_read(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Mark all of the user's notifications as read.

    Args:
        request: The incoming request, used by the rate limiter.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        None.
    """
    notifications_service.mark_all_notifications_as_read(token_user_id, db)
