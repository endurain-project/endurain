from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

import password_reset_tokens.schema as password_reset_tokens_schema
import password_reset_tokens.utils as password_reset_tokens_utils

import auth.password_hasher as auth_password_hasher

import core.database as core_database
import core.apprise as core_apprise

# Define the API router
router = APIRouter()


@router.post("/password-reset/request")
async def request_password_reset(
    request_data: password_reset_tokens_schema.PasswordResetRequest,
    email_service: Annotated[
        core_apprise.AppriseService,
        Depends(core_apprise.get_email_service),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Asynchronously handle a password reset request.

    Attempts to send a password reset email for the provided email address using an
    injected email service and a database session. The endpoint intentionally returns
    a generic success message to avoid revealing whether the provided email exists
    in the system.

    Parameters
    ----------
    request_data : password_reset_tokens_schema.PasswordResetRequest
        Pydantic model containing the email address to send the reset link to.
    email_service : core_apprise.AppriseService
        Dependency-injected service responsible for sending emails.
    db : Session
        Dependency-injected database session.

    Returns
    -------
    dict
        A generic success message:
        {"message": "If the email exists in the system, a password reset link has been sent."}

    Raises
    ------
    HTTPException
        Raised with status_code=status.HTTP_500_INTERNAL_SERVER_ERROR if sending
        the password reset email fails.
    Other Errors
        Validation errors from FastAPI/Pydantic or dependency resolution errors may
        be propagated by the framework.

    Notes
    -----
    - This function is asynchronous.
    - Side effects include attempting to send an email and potentially interacting
      with the database (e.g., creating or updating a password reset token).
    - The generic response is used to mitigate user enumeration attacks.
    """
    success = await password_reset_tokens_utils.send_password_reset_email(
        request_data.email, email_service, db
    )

    # if the email was sent successfully send a generic success message
    if success:
        return {
            "message": "If the email exists in the system, a password reset link has been sent."
        }

    # If the email sending failed, raise an error
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to send password reset email",
    )


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    confirm_data: password_reset_tokens_schema.PasswordResetConfirm,
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
    Confirms a password reset using the provided token and new password.

    Args:
        confirm_data (password_reset_tokens_schema.PasswordResetConfirm):
            Data containing the password reset token and the new password.
        password_hasher (auth_password_hasher.PasswordHasher):
            An instance of the password hasher to use for hashing the new password.
        db (Session):
            Database session dependency.

    Returns:
        dict: A message indicating the password reset was successful.

    Raises:
        HTTPException: If the token is invalid, expired, or the password reset fails.
    """
    # Use the token to reset password
    password_reset_tokens_utils.use_password_reset_token(
        confirm_data.token, confirm_data.new_password, password_hasher, db
    )

    return {"message": "Password reset successful"}
