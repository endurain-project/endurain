"""Persistence operations for password reset tokens."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, select
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.password_reset_tokens.contracts as password_reset_contracts
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.password_reset_tokens.schema as password_reset_schema
import modules.auth.password_reset_tokens.serializers as password_reset_serializers


def create_password_reset_token(
    token: password_reset_schema.PasswordResetToken,
    db: Session,
) -> password_reset_contracts.PasswordResetTokenState:
    """Stage a token row and return its internal state."""
    row = password_reset_models.PasswordResetToken(
        id=token.id,
        user_id=token.user_id,
        token_hash=token.token_hash,
        created_at=token.created_at,
        expires_at=token.expires_at,
        used=token.used,
    )
    db.add(row)
    db.flush()
    return password_reset_serializers.to_state(row)


def password_reset_token_exists(token_hash: str, db: Session) -> bool:
    """Return whether a token with this hash was ever stored, used or not."""
    stmt = select(password_reset_models.PasswordResetToken.id).where(
        password_reset_models.PasswordResetToken.token_hash == token_hash
    )
    return db.execute(stmt).first() is not None


def _usable_token_conditions(token_hash: str) -> tuple[ColumnElement[bool], ...]:
    """Return the conditions under which a token is unused and unexpired."""
    model = password_reset_models.PasswordResetToken
    return (model.token_hash == token_hash, model.used.is_(False), model.expires_at > datetime.now(UTC))


def get_usable_password_reset_token_user_id(token_hash: str, db: Session) -> uuid.UUID | None:
    """Return the owning user id when the token is unused and unexpired, without consuming it."""
    stmt = select(password_reset_models.PasswordResetToken.user_id).where(*_usable_token_conditions(token_hash))
    return db.execute(stmt).scalar_one_or_none()


def claim_password_reset_token(token_hash: str, db: Session) -> uuid.UUID | None:
    """Stage an atomic claim and return the owning user id when the token is valid."""
    stmt = (
        sa_update(password_reset_models.PasswordResetToken)
        .where(*_usable_token_conditions(token_hash))
        .values(used=True)
        .returning(password_reset_models.PasswordResetToken.user_id)
    )
    user_id = db.execute(stmt).scalar_one_or_none()
    db.flush()
    return user_id


def mark_user_password_reset_tokens_used(user_id: uuid.UUID, db: Session) -> int:
    """Stage invalidation of all unused reset tokens for a user."""
    stmt = (
        sa_update(password_reset_models.PasswordResetToken)
        .where(
            password_reset_models.PasswordResetToken.user_id == user_id,
            password_reset_models.PasswordResetToken.used.is_(False),
        )
        .values(used=True)
    )
    matched = core_database.rowcount(db, stmt)
    db.flush()
    return matched


def delete_expired_password_reset_tokens(now: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` reset tokens that expired before ``now`` and return the row count."""
    model = password_reset_models.PasswordResetToken
    expired = select(model.id).where(model.expires_at < now).limit(limit)
    matched = core_database.rowcount(db, sa_delete(model).where(model.id.in_(expired)))
    db.flush()
    return matched
