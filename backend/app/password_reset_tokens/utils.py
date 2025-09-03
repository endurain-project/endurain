import os
import secrets
import hashlib

from datetime import datetime, timedelta, timezone
from fastapi import (
    HTTPException,
    status,
)
from uuid import uuid4

from sqlalchemy.orm import Session

import password_reset_tokens.schema as password_reset_tokens_schema
import password_reset_tokens.crud as password_reset_tokens_crud

import users.user.crud as users_crud

import core.email as core_email
import core.logger as core_logger


def generate_password_reset_token() -> tuple[str, str]:
    """
    Generate a URL-safe password reset token and its SHA-256 hash for storage.
    Returns:
        tuple[str, str]: A tuple (token, token_hash) where:
            - token: a URL-safe, cryptographically secure random token suitable for
              inclusion in password reset links (this raw token is intended to be
              sent to the user).
            - token_hash: the hexadecimal SHA-256 hash of the token, suitable for
              storing in a database instead of the raw token.
    Notes:
        - Do not store or log the raw token; store only the hash (token_hash).
        - When validating a presented token, compute its SHA-256 hex digest and
          compare it to the stored token_hash using a constant-time comparison to
          mitigate timing attacks (e.g., secrets.compare_digest).
        - Consider associating an expiration timestamp and single-use semantics with
          the token to limit its validity window.
        - Token generation relies on the `secrets` module for cryptographic randomness.
    """
    # Generate a random 32-byte token
    token = secrets.token_urlsafe(32)

    # Create a hash of the token for database storage
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    return token, token_hash


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
    token, token_hash = generate_password_reset_token()

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


async def send_password_reset_email(email: str, db: Session) -> bool:
    """
    Send a password reset email to the account associated with the given email address.

    This asynchronous helper:
    - Verifies that the configured email service is available.
    - Looks up the user by email in the provided database session.
    - If the user exists and is active, generates a password reset token and requests
        the email service to send the reset email.
    - Intentionally does not reveal whether the email exists or whether the user is
        inactive: in those cases it returns True to avoid information disclosure.

    Parameters
    ----------
    email : str
            The recipient email address to which the password reset message should be sent.
    db : Session
            Database session used to query user records and to create/persist the password
            reset token.

    Returns
    -------
    bool
            True when the operation is considered successful. This includes the cases
            where the user does not exist or is inactive (to avoid revealing account
            state). For an existing active user, the return value reflects whether the
            email service successfully sent the reset message (True on success, False on failure).

    Raises
    ------
    HTTPException
            If the email service is not configured, raises HTTPException with status
            503 (Service Unavailable).

    Side effects
    ------------
    - May create and persist a password reset token for the user.
    - Invokes the configured email service to send the password reset email.

    Notes
    -----
    - This function is async and must be awaited by callers.
    - Security: the design intentionally avoids leaking whether a given email is
        registered or whether the associated account is active.
    """
    # Check if email service is configured
    if not core_email.email_service.is_configured():
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
    if user.is_active != 1:
        # Don't reveal if user is inactive for security
        return True

    # Generate password reset token
    token = create_password_reset_token(user.id, db)

    # Send email
    success = await core_email.email_service.send_password_reset_email(
        to_email=email,
        user_name=user.name,
        reset_token=token,
    )

    return success


def use_password_reset_token(token: str, new_password: str, db: Session) -> bool:

    # Hash the provided token to find the database record
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Look up the token in the database
    db_token = password_reset_tokens_crud.get_password_reset_token_by_hash(
        token_hash, db
    )

    if not db_token:
        return False

    # Update user password
    try:
        users_crud.edit_user_password(db_token.user_id, new_password, db)

        # Mark token as used
        password_reset_tokens_crud.mark_password_reset_token_used(db_token.id, db)

        return True
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        core_logger.print_to_log(
            f"Error in use_password_reset_token: {err}", "error", exc=err
        )
        return False
