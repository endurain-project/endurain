"""Notification API route handlers."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.notifications.crud as notifications_crud
import modules.notifications.dependencies as notifications_dependencies
import modules.notifications.schema as notifications_schema

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
):
    """
    Retrieve notification count for the user.

    Args:
        _check_scopes: Dependency that checks if the user has the required
            scopes.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        Number of notifications for the user.
    """
    return notifications_crud.get_user_notifications_count(token_user_id, db)


@router.get(
    "/{notification_id}",
    response_model=(notifications_schema.NotificationRead | None),
    status_code=status.HTTP_200_OK,
)
def read_notifications_by_id(
    notification_id: int,
    validate_notification_id: Annotated[
        Callable,
        Depends(notifications_dependencies.validate_notification_id),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Retrieve a notification by ID for the user.

    Args:
        notification_id: Unique ID of the notification.
        validate_notification_id: Dependency that validates the notification ID.
        _check_scopes: Dependency that checks if the user has the required
            scopes.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        Notification object or None if not found.
    """
    return notifications_crud.get_user_notification_by_id(notification_id, token_user_id, db)


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=(list[notifications_schema.NotificationRead] | None),
    status_code=status.HTTP_200_OK,
)
def read_notifications_user_pagination(
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable,
        Depends(core_dependencies.validate_pagination_values),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["notifications:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Retrieve paginated notifications for the user.

    Args:
        page_number: Page number to retrieve.
        num_records: Number of records per page.
        validate_pagination_values: Dependency that validates pagination values.
        _check_scopes: Dependency that checks if the user has the required
            scopes.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        List of notification objects for the page.
    """
    return notifications_crud.get_user_notifications_with_pagination(
        token_user_id,
        db,
        page_number,
        num_records,
    )


@router.put(
    "/{notification_id}/mark_as_read",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
def mark_notification_as_read(
    notification_id: int,
    validate_notification_id: Annotated[
        Callable,
        Depends(notifications_dependencies.validate_notification_id),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["notifications:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Mark a specific notification as read.

    Args:
        notification_id: ID of the notification to mark as read.
        validate_notification_id: Dependency that validates the notification ID.
        _check_scopes: Dependency that checks if the user has the required
            scopes.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        None.
    """
    notifications_crud.mark_notification_as_read(notification_id, token_user_id, db)


@router.put(
    "/mark_all_as_read",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
def mark_all_notifications_as_read(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["notifications:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Mark all of the user's notifications as read.

    Args:
        _check_scopes: Dependency that checks if the user has the required
            scopes.
        token_user_id: ID of the user from the access token.
        db: Database session dependency.

    Returns:
        None.
    """
    notifications_crud.mark_all_notifications_as_read(token_user_id, db)
