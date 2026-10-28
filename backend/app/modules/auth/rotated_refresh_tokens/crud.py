"""Persistence operations for rotated refresh tokens."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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
    """Stage a rotated refresh-token record."""
    row = rotated_token_models.RotatedRefreshToken(**rotated_token.model_dump())
    db.add(row)
    db.flush()
    return rotated_token_schema.RotatedRefreshTokenRead.model_validate(row)


def delete_expired_tokens(cutoff_time: datetime, db: Session) -> int:
    """Stage deletion of expired rotated-token records."""
    result = db.execute(
        delete(rotated_token_models.RotatedRefreshToken).where(
            rotated_token_models.RotatedRefreshToken.expires_at < cutoff_time
        )
    )
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
