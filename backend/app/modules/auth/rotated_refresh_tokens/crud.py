"""Persistence operations for rotated refresh tokens."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.rotated_refresh_tokens.models as rotated_token_models
import modules.auth.rotated_refresh_tokens.schema as rotated_token_schema


def get_rotated_token_by_hash(
    hashed_token: str,
    db: Session,
) -> rotated_token_schema.RotatedRefreshTokenRead | None:
    """Return a rotated token by hash."""
    row = db.execute(
        select(rotated_token_models.RotatedRefreshToken).where(
            rotated_token_models.RotatedRefreshToken.hashed_token == hashed_token
        )
    ).scalar_one_or_none()
    return rotated_token_schema.RotatedRefreshTokenRead.model_validate(row) if row is not None else None


def create_rotated_token(
    rotated_token: rotated_token_schema.RotatedRefreshTokenCreate,
    db: Session,
) -> rotated_token_schema.RotatedRefreshTokenRead:
    """Stage a rotated refresh-token record.

    The hash is unique, so of two concurrent refreshes presenting the same token only one records its
    rotation.

    Args:
        rotated_token: The record to stage.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: When the token was already rotated. The session must be rolled back.
    """
    row = rotated_token_models.RotatedRefreshToken(**rotated_token.model_dump())
    db.add(row)
    try:
        db.flush()
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Refresh token already rotated") from err
    return rotated_token_schema.RotatedRefreshTokenRead.model_validate(row)


def delete_expired_tokens(now: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` rotated-token records whose refresh token expired before ``now``."""
    model = rotated_token_models.RotatedRefreshToken
    expired = select(model.id).where(model.refresh_token_exp < now).limit(limit)
    result = db.execute(delete(model).where(model.id.in_(expired)))
    db.flush()
    return result.rowcount or 0


def delete_by_family(token_family_id: str, db: Session) -> int:
    """Stage deletion of rotated tokens in a family."""
    result = db.execute(
        delete(rotated_token_models.RotatedRefreshToken).where(
            rotated_token_models.RotatedRefreshToken.token_family_id == token_family_id
        )
    )
    db.flush()
    return result.rowcount or 0
