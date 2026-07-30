"""Sign-up tokens router for user registration."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy.orm import Session

import core.apprise as core_apprise
import core.database as core_database
import core.rate_limit as core_rate_limit
import modules.auth.identity_service as auth_identity_service
import modules.auth.sign_up_tokens.schema as sign_up_tokens_schema
import modules.auth.sign_up_tokens.utils as sign_up_tokens_utils
import modules.notifications.utils as notifications_utils
import modules.server_settings.utils as server_settings_utils
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users.utils as users_utils
import modules.websocket.manager as websocket_manager

# Define the API router
router = APIRouter()


@router.post(
    "/sign-up/request",
    status_code=201,
    response_model=sign_up_tokens_schema.SignUpResponse,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
async def signup(
    request: Request,
    user: users_schema.UsersSignup,
    email_service: Annotated[
        core_apprise.AppriseService,
        Depends(core_apprise.get_email_service),
    ],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> sign_up_tokens_schema.SignUpResponse:
    """
    Handle user sign-up request.

    Args:
        request: Incoming HTTP request.
        user: Sign-up payload with user info.
        email_service: Injected email service.
        identity_service: Injected identity service.
        db: Database session.

    Returns:
        Sign-up result with message and flags.

    Raises:
        HTTPException: 403 if sign-up is disabled.
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
    created_user: users_schema.UsersRead = users_crud.create_signup_user(user, server_settings, identity_service, db)

    # Create default data for the user
    users_utils.create_user_default_data(created_user.id, identity_service, db)

    # Return appropriate response based on server configuration
    message = "User created successfully."
    email_verification_required: bool | None = None
    admin_approval_required: bool | None = None

    if server_settings.signup_require_email_verification:
        # Send the sign-up email
        success = await sign_up_tokens_utils.send_sign_up_email(created_user, email_service, db)
        if success:
            message += " Email sent with verification instructions."
        else:
            message += " Failed to send verification email. Please contact support."
        email_verification_required = True
    if server_settings.signup_require_admin_approval:
        message += " Account is pending admin approval."
        admin_approval_required = True
    if not server_settings.signup_require_email_verification and not server_settings.signup_require_admin_approval:
        message += " You can now log in."
    return sign_up_tokens_schema.SignUpResponse(
        message=message,
        email_verification_required=email_verification_required,
        admin_approval_required=admin_approval_required,
    )


@router.post(
    "/sign-up/confirm",
    response_model=sign_up_tokens_schema.SignUpResponse,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
async def verify_email(
    request: Request,
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
) -> sign_up_tokens_schema.SignUpResponse:
    """
    Verify user email via sign-up token.

    Args:
        request: Incoming HTTP request.
        confirm_data: Token confirmation payload.
        email_service: Injected email service.
        websocket_manager: WebSocket notification manager.
        db: Database session.

    Returns:
        Verification result with message and optional flags.

    Raises:
        HTTPException: 412 if email verification is not enabled.
    """
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
        user: users_schema.UsersRead | None = users_crud.get_user_by_id(user_id, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        await sign_up_tokens_utils.send_sign_up_admin_approval_email(user, email_service, db)
        notif_coro = notifications_utils.create_admin_new_sign_up_approval_request_notification(
            user, websocket_manager, db
        )
        await notif_coro

    # Return appropriate response based on server configuration
    message = "Email verified successfully."
    admin_approval_required: bool | None = None
    if server_settings.signup_require_admin_approval:
        message += " Your account is now pending admin approval."
        admin_approval_required = True
    else:
        message += " You can now log in."
    return sign_up_tokens_schema.SignUpResponse(
        message=message,
        admin_approval_required=admin_approval_required,
    )
