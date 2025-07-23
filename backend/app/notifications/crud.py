from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

import notifications.models as notifications_models
import notifications.schema as notifications_schema
import notifications.utils as notifications_utils

import core.logger as core_logger


def get_user_notification_by_id(
    notification_id: int, user_id: int, db: Session
) -> notifications_schema.Notification | None:
    """
    Retrieve a notification for a specific user by notification ID.

    Args:
        notification_id (int): The ID of the notification to retrieve.
        user_id (int): The ID of the user who owns the notification.
        db (Session): The SQLAlchemy database session.

    Returns:
        notifications_schema.Notification | None: The serialized notification object if found, otherwise None.

    Raises:
        HTTPException: If an unexpected error occurs during the database query or serialization.
    """
    try:
        notification = (
            db.query(notifications_models.Notification)
            .filter(
                notifications_models.Notification.user_id == user_id,
                notifications_models.Notification.id == notification_id,
            )
            .first()
        )

        # Check if notification is None and return None if it is
        if notification is None:
            return None

        notification = notifications_utils.serialize_notification(notification)

        # Return the notification
        return notification
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_notification_user_by_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_notifications(
    user_id: int, db: Session
) -> list[notifications_schema.Notification] | None:
    """
    Retrieve all notifications for a specific user by their user ID.

    Args:
        user_id (int): The ID of the user whose notifications are to be retrieved.
        db (Session): The SQLAlchemy database session to use for the query.

    Returns:
        list[notifications_schema.Notification] | None:
            A list of serialized Notification objects for the user, or None if no notifications are found.

    Raises:
        HTTPException: If an unexpected error occurs during the database query,
            raises an HTTP 500 Internal Server Error with a relevant message.
    """
    try:
        notifications = (
            db.query(notifications_models.Notification)
            .filter(notifications_models.Notification.user_id == user_id)
            .all()
        )

        # Check if notifications is None and return None if it is
        if notifications is None:
            return None

        # Serialize each notification
        for notification in notifications:
            notification = notifications_utils.serialize_notification(notification)

        # Return the notifications
        return notifications
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_notifications_user: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_notifications_with_pagination(
    user_id: int, db: Session, page_number: int = 1, num_records: int = 5
) -> list[notifications_schema.Notification] | None:
    """
    Retrieve a paginated list of notifications for a specific user.

    Args:
        user_id (int): The ID of the user whose notifications are to be retrieved.
        db (Session): The SQLAlchemy database session.
        page_number (int, optional): The page number for pagination (default is 1).
        num_records (int, optional): The number of notifications to retrieve per page (default is 5).

    Returns:
        list[notifications_schema.Notification] | None:
            A list of serialized Notification objects for the user, or None if no notifications are found.

    Raises:
        HTTPException: If an internal server error occurs during the retrieval process.
    """
    try:
        # Get the notifications for the user with pagination
        notifications = (
            db.query(notifications_models.Notification)
            .filter(notifications_models.Notification.user_id == user_id)
            .order_by(notifications_models.Notification.created_at.desc())
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if notifications is None and return None if it is
        if notifications is None:
            return None

        # Serialize each notification
        for notification in notifications:
            notification = notifications_utils.serialize_notification(notification)

        # Return the notifications
        return notifications
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_users_notifications_with_pagination: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_notification(notification: notifications_schema.Notification, db: Session):
    """
    Creates a new notification for a specified user and saves it to the database.

    Args:
        notification (notifications_schema.Notification): The notification data to be created.
        db (Session): The SQLAlchemy database session.

    Returns:
        dict: The serialized representation of the newly created notification.

    Raises:
        HTTPException: If an error occurs during the creation process, raises a 500 Internal Server Error.
    """
    try:
        new_notification = notifications_models.Notification(
            user_id=notification.user_id,
            type=notification.type,
            options=notification.options,
            read=False,
            created_at=func.now(),
        )

        # Add the notification to the database
        db.add(new_notification)
        db.commit()
        db.refresh(new_notification)

        notification.id = new_notification.id
        notification.created_at = new_notification.created_at

        notification_serialized = notifications_utils.serialize_notification(
            notification
        )

        # Return the notification
        return notification_serialized
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_notification: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def mark_notification_as_read(
    notification_id: int, user_id: int, db: Session
) -> notifications_schema.Notification | None:
    """
    Marks a notification as read for a specific user.

    Args:
        notification_id (int): The ID of the notification to mark as read.
        user_id (int): The ID of the user who owns the notification.
        db (Session): The SQLAlchemy database session.

    Returns:
        notifications_schema.Notification | None: The serialized notification object if found and updated, otherwise None.

    Raises:
        HTTPException: If an unexpected error occurs during the database query or serialization.
    """
    try:
        notification = (
            db.query(notifications_models.Notification)
            .filter(
                notifications_models.Notification.user_id == user_id,
                notifications_models.Notification.id == notification_id,
            )
            .first()
        )

        # Check if notification is None and return None if it is
        if notification is None:
            return None

        # Update the read status
        notification.read = True
        db.commit()

        # Serialize the updated notification
        notification = notifications_utils.serialize_notification(notification)

        # Return the updated notification
        return notification
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in mark_notification_as_read: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
