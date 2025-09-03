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

# Define the API router
router = APIRouter()


@router.post("/password-reset/request")
async def request_password_reset(
    request_data: password_reset_tokens_schema.PasswordResetRequest,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Handle a request to initiate a password reset for a user account.
    This asynchronous endpoint triggers the process that sends a password reset
    email to the provided address. For security and privacy reasons the
    endpoint always returns a generic success message so that callers cannot
    determine whether the supplied email address is registered in the system.
    Parameters
    - request_data (password_reset_tokens_schema.PasswordResetRequest):
        Pydantic/schema object containing the email address to which the reset
        link should be sent (e.g. {"email": "user@example.com"}).
    - db (Session):
        Database session dependency used by the underlying utilities to look up
        accounts or persist tokens.
    Behavior / Side effects
    - Calls password_reset_tokens_utils.send_password_reset_email(request_data.email, db)
      to create a reset token and send the reset email if appropriate.
    - Intentionally does not disclose whether the email exists to prevent user
      enumeration.
    Return
    - dict: A JSON-serializable dictionary with a generic message:
      {"message": "If the email exists in the system, a password reset link has been sent."}
    Errors
    - Exceptions raised by the underlying email/token utilities (for example,
      database or email service errors) may propagate and result in an error
      response; these are not part of the normal success path.
    Notes
    - This function is async and should be awaited by the framework. Ensure that
      send_password_reset_email handles throttling, token generation, and other
      security considerations (rate limiting, token expiration, single-use tokens).
    """
    await password_reset_tokens_utils.send_password_reset_email(request_data.email, db)
    
    # Always return success to not reveal if email exists
    return {"message": "If the email exists in the system, a password reset link has been sent."}


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    confirm_data: password_reset_tokens_schema.PasswordResetConfirm,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Confirm a password reset using a provided token and new password.
    This asynchronous endpoint handler performs the following steps:
    1. Validates that the provided new password meets the application's
        complexity requirements via session_security.is_password_complexity_valid.
    2. Attempts to consume the provided password reset token and update the
        user's password via password_reset_tokens_utils.use_password_reset_token.
    3. Returns a success message on completion.
    Parameters
    ----------
    confirm_data : password_reset_tokens_schema.PasswordResetConfirm
         Data object containing the password reset token and the new password.
    db : Session
         Database session injected via Depends(core_database.get_db); used to
         look up and persist user and token changes.
    Returns
    -------
    dict
         A JSON-serializable dictionary with a success message:
         {"message": "Password reset successful"}.
    Raises
    ------
    HTTPException
         - HTTP 400 Bad Request if the new password does not meet complexity
            requirements (detail contains the failure reason).
         - HTTP 400 Bad Request if the token is invalid or expired.
    Notes
    -----
    - This function relies on external utilities for password complexity checking
      and token consumption; their side effects include hashing and persisting the
      new password and marking the token as used/invalid.
    - The function is intended to be used as a FastAPI route handler and expects
      dependency injection for the database session.
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
    success = password_reset_tokens_utils.use_password_reset_token(
        confirm_data.token,
        confirm_data.new_password,
        db
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )
    
    return {"message": "Password reset successful"}