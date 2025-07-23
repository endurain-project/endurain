from fastapi import HTTPException, status

from core.database import SessionLocal
from sqlalchemy.orm import Session
import core.logger as core_logger

import notifications.constants as notifications_constants
import notifications.crud as notifications_crud
import notifications.schema as notifications_schema

import users.user.crud as user_crud

import websocket.utils as websocket_utils
import websocket.schema as websocket_schema


def serialize_notification(notification: notifications_schema.Notification):
    # Serialize the notification object
    notification.created_at = notification.created_at.strftime("%Y-%m-%d")

    # Return the serialized notification object
    return notification


async def create_new_activity_notification(
    user_id: int, activity_id: int, websocket_manager: websocket_schema.WebSocketManager
):
    # Create a new database session
    db = SessionLocal()

    try:
        # Create a notification for the new activity
        notification = notifications_crud.create_notification(
            notifications_schema.Notification(
                user_id=user_id,
                type=notifications_constants.TYPE_NEW_ACTIVITY,
                options={"activity_id": activity_id},
            ),
            db,
        )

        # Notify the frontend about the new activity
        json_data = {
            "message": "NEW_ACTIVITY_NOTIFICATION",
            "notification_id": notification.id,
        }
        await websocket_utils.notify_frontend(user_id, websocket_manager, json_data)

        # Return the serialized notification
        return notification
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_new_activity_notification: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
    finally:
        # Ensure the session is closed after use
        db.close()


async def create_new_duplicate_start_time_activity_notification(
    user_id: int, activity_id: int, websocket_manager: websocket_schema.WebSocketManager
):
    # Create a new database session
    db = SessionLocal()

    try:
        # Create a notification for the new activity
        notification = notifications_crud.create_notification(
            notifications_schema.Notification(
                user_id=user_id,
                type=notifications_constants.TYPE_DUPLICATE_ACTIVITY,
                options={"activity_id": activity_id},
            ),
            db,
        )

        # Notify the frontend about the new activity
        json_data = {
            "message": "NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION",
            "notification_id": notification.id,
        }
        await websocket_utils.notify_frontend(user_id, websocket_manager, json_data)

        # Return the serialized notification
        return notification
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_new_duplicate_start_time_activity_notification: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
    finally:
        # Ensure the session is closed after use
        db.close()


async def create_new_follower_request_notification(
    user_id: int,
    target_user_id: int,
    websocket_manager: websocket_schema.WebSocketManager,
    db: Session,
):
    try:
        user = user_crud.get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Create a notification for the new activity
        notification = notifications_crud.create_notification(
            notifications_schema.Notification(
                user_id=target_user_id,
                type=notifications_constants.TYPE_NEW_FOLLOWER_REQUEST,
                options={
                    "user_id": user_id,
                    "user_name": user.name,
                    "user_username": user.username,
                },
            ),
            db,
        )

        # Notify the frontend about the new activity
        json_data = {
            "message": "NEW_FOLLOWER_REQUEST_NOTIFICATION",
            "notification_id": notification.id,
        }
        await websocket_utils.notify_frontend(
            target_user_id, websocket_manager, json_data
        )

        # Return the serialized notification
        return notification
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_new_follower_request_notification: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


async def create_accepted_follower_request_notification(
    user_id: int,
    target_user_id: int,
    websocket_manager: websocket_schema.WebSocketManager,
    db: Session,
):
    try:
        user = user_crud.get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Create a notification for the new activity
        notification = notifications_crud.create_notification(
            notifications_schema.Notification(
                user_id=target_user_id,
                type=notifications_constants.TYPE_NEW_FOLLOWER_REQUEST_ACCEPTED,
                options={
                    "user_id": user_id,
                    "user_name": user.name,
                    "user_username": user.username,
                },
            ),
            db,
        )

        # Notify the frontend about the new activity
        json_data = {
            "message": "NEW_FOLLOWER_REQUEST_ACCEPTED_NOTIFICATION",
            "notification_id": notification.id,
        }
        await websocket_utils.notify_frontend(
            user_id, websocket_manager, json_data
        )

        # Return the serialized notification
        return notification
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_accepted_follower_request_notification: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
