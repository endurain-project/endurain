"""API router for password reset token endpoints."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Request,
    status,
)
from sqlalchemy.orm import Session

import core.database as core_database
import core.rate_limit as core_rate_limit
import modules.auth.identity_service as auth_identity_service
import modules.auth.password_reset_tokens.schema as password_reset_tokens_schema
import modules.auth.password_reset_tokens.utils as password_reset_tokens_utils

# Define the API router
router = APIRouter()


@router.post(
    "/password-reset/request",
    response_model=password_reset_tokens_schema.PasswordResetResponse,
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def request_password_reset(
    request: Request,
    request_data: password_reset_tokens_schema.PasswordResetRequest,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> password_reset_tokens_schema.PasswordResetResponse:
    """
    Handle a password reset request.

    Args:
        request: The HTTP request object.
        request_data: Pydantic model with the email address.
        db: Dependency-injected database session.

    Returns:
        Generic success message to avoid user enumeration.

    Raises:
        HTTPException: 503 if email service is not configured.
    """
    password_reset_tokens_utils.request_password_reset_email(request_data.email, db)

    # Generic success message, whether or not the email exists
    return password_reset_tokens_schema.PasswordResetResponse(
        message="If the email exists in the system, a password reset link has been sent."
    )


@router.post(
    "/password-reset/confirm",
    response_model=password_reset_tokens_schema.PasswordResetResponse,
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
async def confirm_password_reset(
    request: Request,
    confirm_data: password_reset_tokens_schema.PasswordResetConfirm,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> password_reset_tokens_schema.PasswordResetResponse:
    """
    Confirm a password reset using a token and new password.

    Args:
        request: The HTTP request object.
        confirm_data: Token and new password data.
        identity_service: Dependency-injected identity service.
        db: Dependency-injected database session.

    Returns:
        Success message on successful password reset.

    Raises:
        HTTPException: 400 if token is invalid or expired.
        HTTPException: 422 if the new password fails the account's password policy.
        HTTPException: 500 if password reset fails.
    """
    # Use the token to reset password
    password_reset_tokens_utils.use_password_reset_token(
        confirm_data.token, confirm_data.new_password, identity_service, db
    )

    return password_reset_tokens_schema.PasswordResetResponse(message="Password reset successful")
