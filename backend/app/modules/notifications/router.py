"""Notification API route handlers."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
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
    status_code=status.HTTP_200_OK,
)
def read_notifications_number(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> int:
    """Retrieve notification count for the user.

    Args:
        _check_scopes: Dependency that checks if the user has the required
            scopes.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        Number of notifications for the user.
    """
    return notifications_service.count_notifications(token_user_id, db)


@router.get(
    "/{notification_id}",
    response_model=notifications_schema.NotificationRead,
    status_code=status.HTTP_200_OK,
)
def read_notifications_by_id(
    notification_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> notifications_schema.NotificationRead:
    """Retrieve a notification by ID for the user.

    Args:
        notification_id: Unique ID of the notification.
        _check_scopes: Dependency that checks if the user has the required
            scopes.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        The notification.
    """
    return notifications_service.get_notification(notification_id, token_user_id, db)


@router.get(
    "",
    response_model=core_pagination.Page[notifications_schema.NotificationRead],
    status_code=status.HTTP_200_OK,
)
def read_notifications_user_pagination(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
) -> core_pagination.Page[notifications_schema.NotificationRead]:
    """Retrieve paginated notifications for the user.

    Args:
        _check_scopes: Dependency that checks if the user has the required
            scopes.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.
        page: Resolved page number and size.

    Returns:
        The page of notifications with the user's total.
    """
    return notifications_service.list_notifications(
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )


@router.put(
    "/{notification_id}/mark_as_read",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def mark_notification_as_read(
    request: Request,
    notification_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["notifications:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """Mark a specific notification as read.

    Args:
        request: The incoming request, used by the rate limiter.
        notification_id: ID of the notification to mark as read.
        _check_scopes: Dependency that checks if the user has the required
            scopes.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        None.
    """
    notifications_service.mark_notification_as_read(notification_id, token_user_id, db)


@router.put(
    "/mark_all_as_read",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def mark_all_notifications_as_read(
    request: Request,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["notifications:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """Mark all of the user's notifications as read.

    Args:
        request: The incoming request, used by the rate limiter.
        _check_scopes: Dependency that checks if the user has the required
            scopes.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        None.
    """
    notifications_service.mark_all_notifications_as_read(token_user_id, db)
