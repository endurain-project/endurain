from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

import session.schema as session_schema

import users.user.crud as users_crud
import users.user.schema as users_schema
import users.user_integrations.crud as user_integrations_crud
import users.user_default_gear.crud as user_default_gear_crud
import users.user_privacy_settings.crud as users_privacy_settings_crud

import notifications.utils as notifications_utils

import health_targets.crud as health_targets_crud

import sign_up_tokens.utils as sign_up_tokens_utils

import server_settings.utils as server_settings_utils

import core.database as core_database
import core.apprise as core_apprise

import websocket.schema as websocket_schema

# Define the API router
router = APIRouter()


@router.post("/sign-up/request", status_code=201)
async def signup(
    user: users_schema.UserSignup,
    email_service: Annotated[
        core_apprise.AppriseService,
        Depends(core_apprise.get_email_service),
    ],
    websocket_manager: Annotated[
        websocket_schema.WebSocketManager,
        Depends(websocket_schema.get_websocket_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Handle user sign-up: create the user and related default data, enforce server sign-up policies,
    and trigger ancillary actions such as sending verification/approval emails and notifying admins.

    Parameters
    - user (users_schema.UserSignup): The payload containing the user's sign-up information.
    - email_service (core_apprise.AppriseService): Injected email service used to send
        verification and admin approval emails.
    - websocket_manager (websocket_schema.WebSocketManager): Injected manager used to send
        real-time notifications (e.g., admin approval requests).
    - db (Session): Database session/connection used to create the user and related records.

    Behavior and side effects
    - Reads server settings to determine whether sign-up is enabled and whether email verification
        and/or admin approval are required.
    - If sign-up is disabled, raises an HTTPException(403).
    - Creates the user record and several related default records in the database, including:
        - user integrations
        - user privacy settings
        - user health targets
        - user default gear
    - Depending on server settings:
        - If email verification is required (and admin approval is not required):
            - Attempts to send an email with verification instructions to the created user.
            - Adds the "email_verification_required" flag to the returned response and updates
                the human-readable message to reflect email sending success or failure.
            - Note: account creation still occurs even if sending the verification email fails.
        - If admin approval is required:
            - Adds the "admin_approval_required" flag to the returned response and updates
                the human-readable message to indicate the account is pending approval.
            - Sends an admin-approval email and creates a real-time admin notification via
                the websocket manager.
        - If neither email verification nor admin approval is required:
            - Updates the human-readable message to inform the user they can now log in.

    Return
    - dict: A dictionary containing at least a "message" key describing the result.
        Additional keys may be present:
        - "email_verification_required" (bool): Present when email verification must be completed.
        - "admin_approval_required" (bool): Present when admin approval is required.

    Raises
    - HTTPException: Raised with status code 403 when server sign-up is disabled.
    - Any exceptions raised by the underlying CRUD utilities, email service, notification utilities,
        or database session may propagate (e.g., for transaction rollback or upstream error handling).

    Notes
    - This is an async FastAPI route handler intended to be used with dependency injection.
    - The function performs persistent writes and external I/O (sending emails, pushing notifications);
        callers and tests should account for these side effects (e.g., by using transactions, fakes, or mocks).
    """
    # Get server settings to check if signup is enabled
    server_settings = server_settings_utils.get_server_settings(db)

    # Check if signup is enabled
    if not server_settings.signup_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User sign-up is not enabled on this server",
        )

    # Create the user in the database
    created_user = users_crud.create_signup_user(user, server_settings, db)

    # Create the user integrations in the database
    user_integrations_crud.create_user_integrations(created_user.id, db)

    # Create the user privacy settings
    users_privacy_settings_crud.create_user_privacy_settings(created_user.id, db)

    # Create the user health targets
    health_targets_crud.create_health_targets(created_user.id, db)

    # Create the user default gear
    user_default_gear_crud.create_user_default_gear(created_user.id, db)

    # Return appropriate response based on server configuration
    response_data = {"message": "User created successfully."}

    if (
        server_settings.signup_require_email_verification
        and not server_settings.signup_require_admin_approval
    ):
        # Send the sign-up email
        success = await sign_up_tokens_utils.send_sign_up_email(
            created_user, email_service, db
        )

        if success:
            response_data["message"] = (
                response_data["message"] + " Email sent with verification instructions."
            )
        else:
            response_data["message"] = (
                response_data["message"]
                + " Failed to send verification email. Please contact support."
            )
        response_data["email_verification_required"] = True
    if server_settings.signup_require_admin_approval:
        response_data["message"] = (
            response_data["message"] + " Account is pending admin approval."
        )
        response_data["admin_approval_required"] = True

        await sign_up_tokens_utils.send_sign_up_admin_approval_email(
            created_user, email_service, db
        )
        await notifications_utils.create_admin_new_sign_up_approval_request_notification(
            created_user, websocket_manager, db
        )
    if (
        not server_settings.signup_require_email_verification
        and not server_settings.signup_require_admin_approval
    ):
        response_data["message"] = response_data["message"] + " You can now log in."
    return response_data


@router.get("/sign-up/confirm")
async def verify_email(
    confirm_data: session_schema.SignUpResetConfirm,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """Public endpoint for email verification"""
    # Get server settings
    server_settings = server_settings_utils.get_server_settings(db)
    if not server_settings.signup_require_email_verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email verification is not enabled",
        )

    # Verify the email
    user = users_crud.verify_user_email(confirm_data.token, db)

    message = "Email verified successfully."
    if user.pending_admin_approval:
        message += " Your account is now pending admin approval."
    else:
        message += " You can now log in."

    return {
        "message": message,
    }
