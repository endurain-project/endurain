"""CRUD operations for rotated refresh tokens."""

from datetime import datetime
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

import users.users_sessions.rotated_refresh_tokens.models as rotated_token_models
import users.users_sessions.rotated_refresh_tokens.schema as rotated_token_schema

import core.decorators as core_decorators


@core_decorators.handle_db_errors
def get_rotated_token_by_hash(
    hashed_token: str,
    db: Session,
) -> rotated_token_models.RotatedRefreshToken | None:
    """
    Retrieve a rotated token by its hashed value.

    Args:
        hashed_token: The hashed refresh token to search for.
        db: SQLAlchemy database session.

    Returns:
        The RotatedRefreshToken if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = select(rotated_token_models.RotatedRefreshToken).where(
        rotated_token_models.RotatedRefreshToken.hashed_token == hashed_token
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def create_rotated_token(
    rotated_token: rotated_token_schema.RotatedRefreshTokenCreate,
    db: Session,
) -> rotated_token_models.RotatedRefreshToken:
    """
    Store a rotated refresh token in the database.

    Args:
        rotated_token: The rotated token data to store.
        db: SQLAlchemy database session.

    Returns:
        The created RotatedRefreshToken object.

    Raises:
        HTTPException: If database error occurs.
    """
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


@core_decorators.handle_db_errors
def delete_expired_tokens(cutoff_time: datetime, db: Session) -> int:
    """
    Delete rotated tokens older than the cutoff time.

    Args:
        cutoff_time: Tokens with expires_at before this deleted.
        db: SQLAlchemy database session.

    Returns:
        Number of tokens deleted.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = delete(rotated_token_models.RotatedRefreshToken).where(
        rotated_token_models.RotatedRefreshToken.expires_at < cutoff_time
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount


@core_decorators.handle_db_errors
def delete_by_family(token_family_id: str, db: Session) -> int:
    """
    Delete all rotated tokens for a specific token family.

    Args:
        token_family_id: The family ID to delete tokens for.
        db: SQLAlchemy database session.

    Returns:
        Number of tokens deleted.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = delete(rotated_token_models.RotatedRefreshToken).where(
        rotated_token_models.RotatedRefreshToken.token_family_id == token_family_id
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount
