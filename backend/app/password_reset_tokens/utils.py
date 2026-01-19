from datetime import datetime, timedelta, timezone
from fastapi import (
    HTTPException,
    status,
)
from uuid import uuid4
import hashlib

from sqlalchemy.orm import Session

import password_reset_tokens.email_messages as password_reset_tokens_email_messages
import password_reset_tokens.schema as password_reset_tokens_schema
import password_reset_tokens.crud as password_reset_tokens_crud

import users.users.crud as users_crud

import auth.password_hasher as auth_password_hasher

import core.apprise as core_apprise
import core.logger as core_logger

from core.database import SessionLocal


def create_password_reset_token(user_id: int, db: Session) -> str:
    """
    Create and persist a password reset token for a user and return the plain token.

    Parameters
    ----------
    user_id : int
        The ID of the user for whom the password reset token will be created.
    db : Session
        Database session used to persist the token (e.g., an SQLAlchemy Session).

    Returns
    -------
    str
        The plaintext password reset token that should be delivered to the user (for example via email).
        The function stores only a hash of this token in the database.

    Behavior / Side effects
    -----------------------
    - Generates a secure token and a corresponding hash.
    - Creates a PasswordResetToken record with a unique id, user_id, token_hash, created_at,
      expires_at (1 hour after creation), and used flag set to 0.
    - Persists the PasswordResetToken record to the provided database session.

    Security notes
    --------------
    - Treat the returned plaintext token as sensitive; transmit it over secure channels only.
    - Only the token hash is stored in the database to avoid storing secrets in plaintext.
    - When validating a token later, compare the provided token against the stored hash,
      ensure it has not expired, and verify it has not already been used.
    - Consider adding rate limiting, logging, and additional checks to reduce abuse.

    Exceptions
    ----------
    May raise exceptions originating from token generation/hashing utilities or from the database layer
    (e.g., integrity or operational errors). Callers should handle or propagate these exceptions as appropriate.

    Example
    -------
    token = create_password_reset_token(user_id=42, db=session)
    # Send `token` to the user's email. Do not store the plaintext token in persistent storage.
    """
    # Generate token and hash
    token, token_hash = core_apprise.generate_token_and_hash()

    # Create token object
    reset_token = password_reset_tokens_schema.PasswordResetToken(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),  # 1 hour expiration
        used=0,
    )

    # Save to database
    password_reset_tokens_crud.create_password_reset_token(reset_token, db)

    # Return the plain token (not the hash)
    return token


async def send_password_reset_email(
    email: str, email_service: core_apprise.AppriseService, db: Session
) -> bool:
    """
    Asynchronously send a password reset email for the given address.

    This function performs the following steps:
    1. Verifies that the provided email service is configured; if not, raises an HTTP 503.
    2. Attempts to locate the user record for the given email in the provided DB session.
        - For security (to avoid user enumeration), if the user does not exist the function
          returns True and does not indicate existence to the caller.
    3. Verifies the located user is active.
        - If the user is inactive the function returns True for the same security reason.
    4. Creates a password reset token and persists it via create_password_reset_token.
    5. Constructs a frontend reset URL using the email_service.frontend_host and the token.
    6. Builds a default English email subject/body via password_reset_tokens_email_messages
        and delegates actual sending to email_service.send_email.
    7. Returns the boolean result from the email service send operation.

    Parameters
    - email (str): Recipient email address for the password reset message.
    - email_service (core_apprise.AppriseService): An email service instance used to
      construct the frontend host and send the message. Must implement is_configured()
      and an async send_email(...) method that returns a bool.
    - db (Session): SQLAlchemy Session (or equivalent) used to look up the user and
      persist the reset token.

    Returns
    - bool: True when the operation is considered successful. This includes the cases
      where the user does not exist or is inactive (to avoid revealing account existence).
      Otherwise returns the boolean result produced by the email_service.send_email call
      (False typically indicates the email failed to send).

    Raises
    - HTTPException (status 503): If the email service is not configured.
    - Any other exceptions raised by the DB access, token creation, or email service
      may propagate to the caller.

    Side effects and security notes
    - A password reset token is generated and stored when a matching active user is found.
    - The function deliberately avoids disclosing whether an email address maps to a user
      or whether that user is active, to mitigate user enumeration attacks.
    - The reset link contains the raw token; callers should ensure the frontend and token
      handling enforce appropriate expiry and single-use semantics.
    - As an async function, it must be awaited.

    Example
    - await send_password_reset_email("user@example.com", email_service, db)
    """
    # Check if email service is configured
    if not email_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )

    # Find user by email
    user = users_crud.get_user_by_email(email, db)
    if not user:
        # Don't reveal if email exists or not for security
        return True

    # Check if user is active
    if not user.active:
        # Don't reveal if user is inactive for security
        return True

    # Generate password reset token
    token = create_password_reset_token(user.id, db)

    # Generate reset link
    reset_link = f"{email_service.frontend_host}/reset-password?token={token}"

    # use default email message in English
    subject, html_content, text_content = (
        password_reset_tokens_email_messages.get_password_reset_email_en(
            user.name, reset_link, email_service
        )
    )

    # Send email
    return await email_service.send_email(
        to_emails=[email],
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )


def use_password_reset_token(
    token: str,
    new_password: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
):
    """
    Use a password reset token to update a user's password and mark the token as used.

    The function:
    - Hashes the provided plain-text token (SHA-256) and looks up the corresponding
        password reset record in the database.
    - If no matching record is found, raises an HTTPException with status 400.
    - Delegates password update to users_crud.edit_user_password.
    - Marks the token as used via password_reset_tokens_crud.mark_password_reset_token_used.
    - Logs unexpected errors and raises an HTTPException with status 500 on failure.

    Parameters:
    - token (str): The plain-text password reset token supplied by the user. This
        function will hash it before database lookup.
    - new_password (str): The new plain-text password to set for the user. Password
        validation/hashing is expected to be handled by the underlying users_crud.
    - password_hasher (auth_password_hasher.PasswordHasher): An instance of the
        password hasher to use when updating the user's password.
    - db (Session): An active SQLAlchemy Session (or equivalent) used for DB operations.
        Transaction management (commit/rollback) is expected to be handled by the caller
        or the CRUD functions.

    Returns:
    - None

    Side effects:
    - Updates the user's password in the database.
    - Marks the password reset token record as used/consumed.
    - Writes error information to the application log on unexpected failures.

    Exceptions:
    - Raises HTTPException(status_code=400) when the token is invalid or expired.
    - Re-raises any HTTPException raised by underlying CRUD functions.
    - Raises HTTPException(status_code=500) for unexpected internal errors.

    Security notes:
    - The token is hashed (SHA-256) before lookup to avoid storing/using the plain token.
    - Ensure new_password meets application password policy and that users_crud
        securely hashes and salts passwords before persisting.
    """
    # Hash the provided token to find the database record
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Look up the token in the database
    db_token = password_reset_tokens_crud.get_password_reset_token_by_hash(
        token_hash, db
    )

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
        )

    # Update user password
    try:
        users_crud.edit_user_password(
            db_token.user_id, new_password, password_hasher, db
        )

        # Mark token as used
        password_reset_tokens_crud.mark_password_reset_token_used(db_token.id, db)
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        core_logger.print_to_log(
            f"Error in use_password_reset_token: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_invalid_tokens_from_db():
    """
    Remove expired password reset tokens from the database.

    Opens a new database session, calls the password_reset_tokens_crud layer to
    delete any expired password reset tokens, and logs the number of deleted
    tokens if one or more were removed. The database session is guaranteed to be
    closed whether the operation succeeds or an exception is raised.

    Behavior:
    - Invokes password_reset_tokens_crud.delete_expired_password_reset_tokens(db),
        which should return the number of deleted tokens (int).
    - If the returned count is greater than zero, logs an informational message
        via core_logger.print_to_log_and_console.
    - Always closes the database session in a finally block.

    Returns:
    - None

    Exceptions:
    - Exceptions raised by the CRUD layer or the logger will propagate to the
        caller, but the database session will still be closed before propagation.

    Notes:
    - This function performs destructive, persistent changes (deletions) and is
        intended to be run as part of maintenance (for example, a scheduled task).
    - The operation is effectively idempotent: running it repeatedly when there
        are no expired tokens will have no further effect.
    """
    # Create a new database session using context manager
    with SessionLocal() as db:
        # Get num tokens deleted
        num_deleted = password_reset_tokens_crud.delete_expired_password_reset_tokens(
            db
        )

        # Log the number of deleted tokens
        if num_deleted > 0:
            core_logger.print_to_log_and_console(
                f"Deleted {num_deleted} expired password reset tokens", "info"
            )
