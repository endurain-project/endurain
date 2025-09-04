from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session
from datetime import datetime, timezone

import password_reset_tokens.schema as password_reset_tokens_schema
import password_reset_tokens.models as password_reset_tokens_models

import core.logger as core_logger


def create_password_reset_token(
    token: password_reset_tokens_schema.PasswordResetToken, db: Session
) -> password_reset_tokens_models.PasswordResetToken:
    """
    Create and persist a new password reset token record in the database.

    This function constructs a PasswordResetToken ORM model from the provided
    schema object, adds it to the given SQLAlchemy session, commits the
    transaction, refreshes the instance from the database, and returns the
    persisted model instance.

    Parameters:
        token (password_reset_tokens_schema.PasswordResetToken): A schema object
            containing the token data to be stored. Expected attributes include
            id, user_id, token_hash, created_at, expires_at, and used.
        db (Session): An active SQLAlchemy Session used to persist the model.

    Returns:
        password_reset_tokens_models.PasswordResetToken: The persisted ORM model
        instance representing the created password reset token, refreshed from
        the database to include any defaults or database-side generated values.

    Side effects:
        - Adds a new PasswordResetToken instance to the provided DB session.
        - Commits the session, causing the INSERT to be executed.
        - Refreshes the instance from the database.

    Errors:
        On any exception during add/commit/refresh the session is rolled back,
        the error is logged, and an HTTPException with status_code
        500 (Internal Server Error) is raised (the original exception is chained).
    """
    try:
        # Create a new password reset token
        db_token = password_reset_tokens_models.PasswordResetToken(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            created_at=token.created_at,
            expires_at=token.expires_at,
            used=token.used,
        )

        # Add the token to the database
        db.add(db_token)
        db.commit()
        db.refresh(db_token)

        # Return the token
        return db_token
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_password_reset_token: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_password_reset_token_by_hash(
    token_hash: str, db: Session
) -> password_reset_tokens_models.PasswordResetToken | None:
    try:
        # Get the token from the database
        db_token = (
            db.query(password_reset_tokens_models.PasswordResetToken)
            .filter(
                and_(
                    password_reset_tokens_models.PasswordResetToken.token_hash
                    == token_hash,
                    password_reset_tokens_models.PasswordResetToken.used == False,
                    password_reset_tokens_models.PasswordResetToken.expires_at
                    > datetime.now(timezone.utc),
                )
            )
            .first()
        )

        # Return the token (can be None if not found)
        return db_token
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_password_reset_token_by_hash: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def mark_password_reset_token_used(
    token_id: str, db: Session
) -> password_reset_tokens_models.PasswordResetToken | None:
    """
    Mark a password reset token as used.

    This function looks up a PasswordResetToken by its identifier, sets its `used`
    attribute to True, and commits the change to the database.

    Parameters
    ----------
    token_id : str
        The unique identifier of the password reset token to mark as used.
    db : Session
        An active SQLAlchemy Session used to query and persist changes.

    Returns
    -------
    password_reset_tokens_models.PasswordResetToken | None
        The updated PasswordResetToken instance if found and updated; otherwise
        None if no token with the given id exists.

    Side effects
    ------------
    - If the token is found, its `used` field is set to True and the change is
      committed to the database.
    - On unexpected errors, the transaction is rolled back, the error is logged
      (via core_logger), and an HTTPException with status 500 is raised.

    Exceptions
    ----------
    HTTPException
        Raised with status code 500 (Internal Server Error) when an unexpected
        error occurs during the database operation.
    """
    try:
        # Get the token from the database
        db_token = (
            db.query(password_reset_tokens_models.PasswordResetToken)
            .filter(password_reset_tokens_models.PasswordResetToken.id == token_id)
            .first()
        )

        if db_token:
            # Mark the token as used
            db_token.used = True
            db.commit()

        return db_token
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in mark_password_reset_token_used: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_expired_password_reset_tokens(db: Session):
    """
    Delete expired password reset tokens from the database.

    This function removes all PasswordResetToken records whose `expires_at`
    timestamp is strictly earlier than the current UTC time (datetime.now(timezone.utc)).
    On success the transaction is committed and the number of deleted rows is returned.
    If any exception occurs during the operation, the session is rolled back,
    the error is logged via core_logger.print_to_log, and an HTTPException with
    status 500 (Internal Server Error) is raised.

    Parameters
    ----------
    db : Session
        An active SQLAlchemy session used to query, delete, and commit changes.

    Returns
    -------
    int
        The number of password reset token rows deleted.

    Raises
    ------
    fastapi.HTTPException
        Raised with status_code=500 if an unexpected error occurs while deleting
        tokens or committing the transaction. The original exception is logged
        and the transaction is rolled back before raising.
    """
    try:
        # Delete expired tokens
        num_deleted = (
            db.query(password_reset_tokens_models.PasswordResetToken)
            .filter(
                password_reset_tokens_models.PasswordResetToken.expires_at
                < datetime.now(timezone.utc)
            )
            .delete()
        )

        # Commit the transaction
        db.commit()

        return num_deleted
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in delete_expired_password_reset_tokens: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
