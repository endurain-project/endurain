"""CRUD operations for rotated refresh tokens."""

from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import users.users_session.rotated_refresh_tokens.models as rotated_token_models
import users.users_session.rotated_refresh_tokens.schema as rotated_token_schema
import core.logger as core_logger


def get_rotated_token_by_hash(
    hashed_token: str, db: Session
) -> rotated_token_models.RotatedRefreshToken | None:
    """
    Retrieve a rotated token by its hashed value.

    Args:
        hashed_token: The hashed refresh token to search for.
        db: Database session.

    Returns:
        The RotatedRefreshToken if found, None otherwise.

    Raises:
        HTTPException: If an error occurs during retrieval (500).
    """
    try:
        return (
            db.query(rotated_token_models.RotatedRefreshToken)
            .filter(
                rotated_token_models.RotatedRefreshToken.hashed_token == hashed_token
            )
            .first()
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_rotated_token_by_hash: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve rotated token",
        ) from err


def create_rotated_token(
    rotated_token: rotated_token_schema.RotatedRefreshTokenCreate,
    db: Session,
) -> rotated_token_models.RotatedRefreshToken:
    """
    Store a rotated refresh token in the database.

    Args:
        rotated_token: The rotated token data to store.
        db: Database session.

    Returns:
        The created RotatedRefreshToken object.

    Raises:
        HTTPException: If an error occurs during creation (500).
    """
    try:
        db_rotated_token = rotated_token_models.RotatedRefreshToken(
            token_family_id=rotated_token.token_family_id,
            hashed_token=rotated_token.hashed_token,
            rotation_count=rotated_token.rotation_count,
            rotated_at=rotated_token.rotated_at,
            expires_at=rotated_token.expires_at,
        )

        db.add(db_rotated_token)
        db.commit()
        db.refresh(db_rotated_token)

        return db_rotated_token
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in create_rotated_token: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store rotated token",
        ) from err


def delete_expired_tokens(cutoff_time: datetime, db: Session) -> int:
    """
    Delete rotated tokens older than the cutoff time.

    Args:
        cutoff_time: Tokens with expires_at before this will be deleted.
        db: Database session.

    Returns:
        Number of tokens deleted.

    Raises:
        HTTPException: If an error occurs during deletion (500).
    """
    try:
        num_deleted = (
            db.query(rotated_token_models.RotatedRefreshToken)
            .filter(rotated_token_models.RotatedRefreshToken.expires_at < cutoff_time)
            .delete()
        )

        db.commit()
        return num_deleted
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in delete_expired_tokens: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete expired tokens",
        ) from err


def delete_by_family(token_family_id: str, db: Session) -> int:
    """
    Delete all rotated tokens for a specific token family.

    Args:
        token_family_id: The family ID to delete tokens for.
        db: Database session.

    Returns:
        Number of tokens deleted.

    Raises:
        HTTPException: If an error occurs during deletion (500).
    """
    try:
        num_deleted = (
            db.query(rotated_token_models.RotatedRefreshToken)
            .filter(
                rotated_token_models.RotatedRefreshToken.token_family_id
                == token_family_id
            )
            .delete()
        )

        db.commit()
        return num_deleted
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(f"Error in delete_by_family: {err}", "error", exc=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete tokens by family",
        ) from err
