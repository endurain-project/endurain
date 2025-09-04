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

import session.security as session_security

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
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Confirm a password reset using a one-time token.

    Validates the provided new password against configured complexity rules and, if
    valid, delegates to the password reset token utility to apply the new password.

    Parameters:
        confirm_data (password_reset_tokens_schema.PasswordResetConfirm):
            Object containing the reset token and the requested new password
            (expected attributes: 'token', 'new_password').
        db (Session):
            Database session provided by dependency injection (core_database.get_db).

    Returns:
        dict: A JSON-serializable mapping with a success message, e.g.:
            {"message": "Password reset successful"}

    Raises:
        HTTPException:
            - Raised with status 400 if the new password does not meet complexity
              requirements. The response detail contains the validation message.
            - May be raised by password_reset_tokens_utils.use_password_reset_token
              for problems such as an invalid, expired, or already-consumed token,
              or for database-related errors.

    Side effects:
        - Updates the user's password in persistent storage.
        - Invalidates/consumes the provided password reset token.
        - Persists changes using the provided database session.

    Notes:
        - Password complexity rules are enforced by
          session_security.is_password_complexity_valid.
        - Token application, user lookup, password hashing, and database commits
          are handled by password_reset_tokens_utils.use_password_reset_token.
    """
    # Check if the password meets the complexity requirements
    is_valid, message = session_security.is_password_complexity_valid(
        confirm_data.new_password
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    # Use the token to reset password
    password_reset_tokens_utils.use_password_reset_token(
        confirm_data.token, confirm_data.new_password, db
    )

    return {"message": "Password reset successful"}
