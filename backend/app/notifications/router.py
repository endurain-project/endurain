from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session

import auth.security as auth_security

import notifications.dependencies as notifications_dependencies
import notifications.crud as notifications_crud
import notifications.schema as notifications_schema

import core.database as core_database
import core.dependencies as core_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/number",
    response_model=int,
)
async def read_notifications_number(
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Retrieve the number of notifications for the authenticated user.

    Args:
        token_user_id (int): The ID of the user, extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        int: The number of notifications for the user. Returns 0 if no notifications are found.
    """
    notifications = notifications_crud.get_user_notifications(token_user_id, db)
    if notifications is None:
        return 0
    return len(notifications)


@router.get(
    "/{notification_id}",
    response_model=notifications_schema.Notification | None,
)
async def read_notifications_by_id(
    notification_id: int,
    validate_notification_id: Annotated[
        Callable, Depends(notifications_dependencies.validate_notification_id)
    ],
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Retrieve a specific notification by its ID for the authenticated user.

    Args:
        notification_id (int): The unique identifier of the notification to retrieve.
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        The notification object corresponding to the given notification_id and user, or None if not found.
    """
    return notifications_crud.get_user_notification_by_id(
        notification_id, token_user_id, db
    )


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=list[notifications_schema.Notification] | None,
)
async def read_notifications_user_pagination(
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
    ],
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Retrieve a paginated list of notifications for the authenticated user.

    Args:
        page_number (int): The page number to retrieve.
        num_records (int): The number of notification records per page.
        token_user_id (int): The ID of the authenticated user, extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        List[Notification]: A list of notification objects for the specified page and user.
    """
    # Return the notifications
    return notifications_crud.get_user_notifications_with_pagination(
        token_user_id, db, page_number, num_records
    )


@router.put(
    "/{notification_id}/mark_as_read",
)
async def mark_notification_as_read(
    notification_id: int,
    validate_notification_id: Annotated[
        Callable, Depends(notifications_dependencies.validate_notification_id)
    ],
    token_user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Mark a specific notification as read.

    Args:
        notification_id (int): The ID of the notification to mark as read.
        token_user_id (int): The ID of the authenticated user, extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        None: The notification is marked as read in the database.
    """
    notifications_crud.mark_notification_as_read(notification_id, token_user_id, db)
