from fastapi import HTTPException, status

from core.database import SessionLocal
from sqlalchemy.orm import Session
import core.logger as core_logger

import notifications.constants as notifications_constants
import notifications.crud as notifications_crud
import notifications.schema as notifications_schema

import users.users.crud as users_crud
import users.users.models as users_models
import users.users.utils as users_utils

import websocket.utils as websocket_utils
import websocket.manager as websocket_manager


def serialize_notification(notification: notifications_schema.Notification):
    # Serialize the notification object
    notification.created_at = notification.created_at.strftime("%Y-%m-%d")

    # Return the serialized notification object
    return notification


async def create_new_activity_notification(
    user_id: int,
    activity_id: int,
    websocket_manager: websocket_manager.WebSocketManager,
):
    # Create a new database session using context manager
    with SessionLocal() as db:
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


async def create_new_duplicate_start_time_activity_notification(
    user_id: int,
    activity_id: int,
    websocket_manager: websocket_manager.WebSocketManager,
):
    # Create a new database session using context manager
    with SessionLocal() as db:
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


async def create_new_follower_request_notification(
    user_id: int,
    target_user_id: int,
    websocket_manager: websocket_manager.WebSocketManager,
    db: Session,
):
    try:
        user = users_crud.get_user_by_id(user_id, db)
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
    websocket_manager: websocket_manager.WebSocketManager,
    db: Session,
):
    try:
        user = users_crud.get_user_by_id(user_id, db)
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
        await websocket_utils.notify_frontend(user_id, websocket_manager, json_data)

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


async def create_admin_new_sign_up_approval_request_notification(
    user: users_models.Users,
    websocket_manager: websocket_manager.WebSocketManager,
    db: Session,
):
    try:
        admins = users_utils.get_admin_users_or_404(db)

        # Send notification to all admin users
        for admin in admins:
            # Create a notification for the new sign up request
            notification = notifications_crud.create_notification(
                notifications_schema.Notification(
                    user_id=admin.id,
                    type=notifications_constants.TYPE_ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST,
                    options={
                        "user_id": user.id,
                        "user_name": user.name,
                        "user_username": user.username,
                    },
                ),
                db,
            )

            # Notify the frontend about the new sign up request
            json_data = {
                "message": "ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_NOTIFICATION",
                "notification_id": notification.id,
            }
            await websocket_utils.notify_frontend(
                admin.id, websocket_manager, json_data
            )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_admin_new_sign_up_approval_request_notification: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
