from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session
from datetime import datetime, timezone

import sign_up_tokens.schema as sign_up_tokens_schema
import sign_up_tokens.models as sign_up_tokens_models

import core.logger as core_logger


def create_sign_up_token(
    token: sign_up_tokens_schema.SignUpToken, db: Session
) -> sign_up_tokens_models.SignUpToken:
    """
    Create and persist a sign-up token in the database.

    Parameters
    ----------
    token : sign_up_tokens_schema.SignUpToken
        Schema object containing the token data to store. Expected fields include
        id, user_id, token_hash, created_at, expires_at, and used.
    db : Session
        SQLAlchemy session used for the database transaction.

    Returns
    -------
    sign_up_tokens_models.SignUpToken
        The persisted SignUpToken model instance refreshed from the database so
        any DB-generated values (defaults, timestamps, etc.) are populated.

    Side effects
    ------------
    - Adds a new SignUpToken row to the database and commits the transaction on success.
    - Calls db.refresh() to populate the returned model with persisted state.
    - On error, rolls back the transaction and logs the exception via core_logger.print_to_log().

    Raises
    ------
    HTTPException
        An HTTPException with status_code 500 (Internal Server Error) is raised if
        any exception occurs during creation. The original exception is chained
        to the raised HTTPException.
    """
    try:
        # Create a new sign up token
        db_token = sign_up_tokens_models.SignUpToken(
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
            f"Error in create_sign_up_token: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_sign_up_token_by_hash(
    token_hash: str, db: Session
) -> sign_up_tokens_models.SignUpToken | None:
    """
    Retrieve an unused, unexpired SignUpToken matching the provided token hash.

    Parameters
    ----------
    token_hash : str
        The hashed token value to look up in the database.
    db : Session
        The SQLAlchemy Session used to perform the query.

    Returns
    -------
    sign_up_tokens_models.SignUpToken | None
        The SignUpToken model instance if a matching token exists, is not marked as used,
        and has an expires_at timestamp later than the current UTC time. Returns None when
        no valid token is found.

    Raises
    ------
    HTTPException
        If an unexpected error occurs during the database query, the exception is logged
        and an HTTPException with status code 500 (Internal Server Error) is raised.

    Notes
    -----
    - The function filters tokens by: token_hash equality, used == False, and expires_at > now (UTC).
    - Any caught exception is logged via core_logger.print_to_log before raising the HTTPException.
    """
    try:
        # Get the token from the database
        db_token = (
            db.query(sign_up_tokens_models.SignUpToken)
            .filter(
                and_(
                    sign_up_tokens_models.SignUpToken.token_hash == token_hash,
                    sign_up_tokens_models.SignUpToken.used == False,
                    sign_up_tokens_models.SignUpToken.expires_at
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
            f"Error in get_sign_up_token_by_hash: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def mark_sign_up_token_used(
    token_id: str, db: Session
) -> sign_up_tokens_models.SignUpToken | None:
    """
    Mark a sign-up token as used.

    This function looks up a SignUpToken by its ID and, if found, sets its 'used'
    attribute to True and commits the change to the provided SQLAlchemy session.
    If no token with the given ID exists, the function returns None and does not
    modify the database.

    Args:
        token_id (str): The unique identifier of the sign-up token to mark as used.
        db (Session): An active SQLAlchemy Session used to query and persist changes.

    Returns:
        sign_up_tokens_models.SignUpToken | None: The updated SignUpToken instance
        if it was found (with 'used' set to True), otherwise None.

    Raises:
        HTTPException: If an unexpected error occurs while accessing or committing
        to the database, the function rolls back the transaction, logs the error,
        and raises an HTTPException with status code 500 (Internal Server Error).

    Side effects:
        - Commits the transaction when a token is found and updated.
        - Rolls back the transaction on exception.
        - Logs exceptions via core_logger.print_to_log.

    Notes:
        - The caller is responsible for providing a managed Session. This function
          performs commit/rollback and therefore affects session state.
        - For concurrent scenarios, consider appropriate locking or transactional
          isolation to avoid race conditions when marking tokens as used.
    """
    try:
        # Get the token from the database
        db_token = (
            db.query(sign_up_tokens_models.SignUpToken)
            .filter(sign_up_tokens_models.SignUpToken.id == token_id)
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
            f"Error in mark_sign_up_token_used: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_expired_sign_up_tokens(db: Session):
    """
    Delete expired SignUpToken records from the database.

    This function deletes all SignUpToken rows whose `expires_at` is earlier than
    the current UTC time. It performs the deletion using the provided SQLAlchemy
    Session, commits the transaction on success, and returns the number of rows
    deleted. If an error occurs, the transaction is rolled back, the error is
    logged, and an HTTPException with a 500 status code is raised (the original
    exception is preserved for chaining).

    Args:
        db (Session): An active SQLAlchemy Session used to execute the delete and
            commit operations.

    Returns:
        int: The number of SignUpToken records removed by the operation.

    Raises:
        HTTPException: Raised with status_code=500 if any unexpected error occurs
            during deletion or commit.

    Side effects and notes:
        - Permanently removes matching rows from the database.
        - Commits the transaction on success; rolls back the transaction on error.
        - Uses UTC-aware comparison (datetime.now(timezone.utc)) to evaluate expiration.
        - Uses a bulk query-level delete; such bulk operations may bypass ORM-level
          cascades, event hooks, and may not synchronize in-memory objects in the
          session. If the session holds SignUpToken instances, consider session
          synchronization or expiring/refreshing those objects after the operation.
    """
    try:
        # Delete expired tokens
        num_deleted = (
            db.query(sign_up_tokens_models.SignUpToken)
            .filter(
                sign_up_tokens_models.SignUpToken.expires_at
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
            f"Error in delete_expired_sign_up_tokens: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
