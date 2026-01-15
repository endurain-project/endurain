from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

import users.user.crud as users_crud
import users.user.utils as users_utils
import users.user.schema as users_schema

import notifications.utils as notifications_utils

import sign_up_tokens.utils as sign_up_tokens_utils
import sign_up_tokens.schema as sign_up_tokens_schema

import auth.password_hasher as auth_password_hasher

import server_settings.utils as server_settings_utils

import core.database as core_database
import core.apprise as core_apprise

import websocket.manager as websocket_manager

# Define the API router
router = APIRouter()


@router.post("/sign-up/request", status_code=201)
async def signup(
    user: users_schema.UserSignup,
    email_service: Annotated[
        core_apprise.AppriseService,
        Depends(core_apprise.get_email_service),
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
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
    - websocket_manager (websocket_manager.WebSocketManager): Injected manager used to send
        real-time notifications (e.g., admin approval requests).
    - password_hasher (auth_password_hasher.PasswordHasher): Injected password hasher used to hash user passwords.
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
    server_settings = server_settings_utils.get_server_settings_or_404(db)

    # Check if signup is enabled
    if not server_settings.signup_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User sign-up is not enabled on this server",
        )

    # Create the user in the database
    created_user = users_crud.create_signup_user(
        user, server_settings, password_hasher, db
    )

    # Create default data for the user
    users_utils.create_user_default_data(created_user.id, db)

    # Return appropriate response based on server configuration
    response_data = {"message": "User created successfully."}

    if server_settings.signup_require_email_verification:
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
    if (
        not server_settings.signup_require_email_verification
        and not server_settings.signup_require_admin_approval
    ):
        response_data["message"] = response_data["message"] + " You can now log in."
    return response_data


@router.post("/sign-up/confirm")
async def verify_email(
    confirm_data: sign_up_tokens_schema.SignUpConfirm,
    email_service: Annotated[
        core_apprise.AppriseService,
        Depends(core_apprise.get_email_service),
    ],
    websocket_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get server settings
    server_settings = server_settings_utils.get_server_settings_or_404(db)
    if not server_settings.signup_require_email_verification:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="Email verification is not enabled",
        )

    # Verify the email
    user_id = sign_up_tokens_utils.use_sign_up_token(confirm_data.token, db)
    users_crud.verify_user_email(user_id, server_settings, db)

    if email_service.is_configured():
        user = users_crud.get_user_by_id(user_id, db)
        await sign_up_tokens_utils.send_sign_up_admin_approval_email(
            user, email_service, db
        )
        await notifications_utils.create_admin_new_sign_up_approval_request_notification(
            user, websocket_manager, db
        )

    # Return appropriate response based on server configuration
    response_data = {"message": "Email verified successfully."}
    if server_settings.signup_require_admin_approval:
        response_data["message"] += " Your account is now pending admin approval."
        response_data["admin_approval_required"] = True
    else:
        response_data["message"] += " You can now log in."

    return response_data
