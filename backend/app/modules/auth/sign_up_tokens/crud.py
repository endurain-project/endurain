"""CRUD operations for sign-up tokens."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CursorResult, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.auth.sign_up_tokens.models as sign_up_tokens_models
import modules.auth.sign_up_tokens.schema as sign_up_tokens_schema


@core_decorators.handle_db_errors
def get_sign_up_token_by_hash(token_hash: str, db: Session) -> sign_up_tokens_models.SignUpToken | None:
    """Retrieve an unused, unexpired token matching the hash.

    Args:
        token_hash: The hashed token value to look up.
        db: SQLAlchemy database session.

    Returns:
        The matching SignUpToken if found and valid,
        None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(sign_up_tokens_models.SignUpToken).where(
        sign_up_tokens_models.SignUpToken.token_hash == token_hash,
        sign_up_tokens_models.SignUpToken.used.is_(False),
        sign_up_tokens_models.SignUpToken.expires_at > datetime.now(UTC),
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def create_sign_up_token(
    token: sign_up_tokens_schema.SignUpToken,
    db: Session,
) -> sign_up_tokens_models.SignUpToken:
    """Create and persist a new sign-up token.

    Args:
        token: Schema object with token data to persist.
        db: SQLAlchemy database session.

    Returns:
        The persisted SignUpToken ORM instance.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    db_token = sign_up_tokens_models.SignUpToken(
        id=token.id,
        user_id=token.user_id,
        token_hash=token.token_hash,
        created_at=token.created_at,
        expires_at=token.expires_at,
        used=token.used,
    )
    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token


@core_decorators.handle_db_errors
def mark_sign_up_token_used(token_id: str, db: Session) -> sign_up_tokens_models.SignUpToken | None:
    """Mark a sign-up token as used.

    Args:
        token_id: The unique identifier of the token.
        db: SQLAlchemy database session.

    Returns:
        Updated SignUpToken instance if found,
        None otherwise.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    stmt = select(sign_up_tokens_models.SignUpToken).where(
        sign_up_tokens_models.SignUpToken.id == token_id,
    )
    db_token = db.execute(stmt).scalar_one_or_none()

    if db_token:
        db_token.used = True
        db.commit()
        db.refresh(db_token)

    return db_token


@core_decorators.handle_db_errors
def delete_expired_sign_up_tokens(db: Session) -> int:
    """Delete all expired sign-up tokens.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Number of deleted rows.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    stmt = sa_delete(sign_up_tokens_models.SignUpToken).where(
        sign_up_tokens_models.SignUpToken.expires_at < datetime.now(UTC)
    )
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()
    return result.rowcount
