"""Persistence operations for rotated refresh tokens."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.key_rotation as core_key_rotation
import modules.auth.rotated_refresh_tokens.models as rotated_token_models
import modules.auth.rotated_refresh_tokens.schema as rotated_token_schema


def get_rotated_token_by_hashes(
    hashed_tokens: Sequence[str],
    db: Session,
) -> rotated_token_schema.RotatedRefreshTokenRead | None:
    """Return a rotated token by any of its digests, one per key of the key list."""
    row = db.execute(
        select(rotated_token_models.RotatedRefreshToken).where(
            rotated_token_models.RotatedRefreshToken.hashed_token.in_(hashed_tokens)
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
    matched = core_database.rowcount(db, delete(model).where(model.id.in_(expired)))
    db.flush()
    return matched


def clear_expired_replacements(now: datetime, limit: int, db: Session) -> int:
    """Stage clearing the replacement token of up to ``limit`` records whose grace window ended before ``now``.

    The record itself stays, so a replay of the rotated token is still recognised as reuse.
    """
    model = rotated_token_models.RotatedRefreshToken
    expired = select(model.id).where(model.expires_at < now, model.replacement_refresh_token.is_not(None)).limit(limit)
    matched = core_database.rowcount(
        db,
        update(model)
        .where(model.id.in_(expired))
        .values(replacement_refresh_token=None, replacement_refresh_token_exp=None),
    )
    db.flush()
    return matched


def delete_by_family(token_family_id: str, db: Session) -> int:
    """Stage deletion of rotated tokens in a family."""
    matched = core_database.rowcount(
        db,
        delete(rotated_token_models.RotatedRefreshToken).where(
            rotated_token_models.RotatedRefreshToken.token_family_id == token_family_id
        ),
    )
    db.flush()
    return matched


def stage_reencrypt_batch_tokens(after_id: int | None, limit: int, db: Session) -> core_key_rotation.BatchResult[int]:
    """Stage the re-encryption of up to ``limit`` tokens rows after ``after_id`` (flushed, not committed)."""
    model = rotated_token_models.RotatedRefreshToken
    return core_key_rotation.stage_reencrypt_batch(
        model, model.id, (model.replacement_refresh_token,), after_id, limit, db
    )
