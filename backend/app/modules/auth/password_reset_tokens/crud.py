"""Persistence operations for password reset tokens."""

from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

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


def get_password_reset_token_by_hash(
    token_hash: str, db: Session
) -> password_reset_contracts.PasswordResetTokenState | None:
    """Return an unused, unexpired token state matching the hash."""
    stmt = select(password_reset_models.PasswordResetToken).where(
        password_reset_models.PasswordResetToken.token_hash == token_hash,
        password_reset_models.PasswordResetToken.used.is_(False),
        password_reset_models.PasswordResetToken.expires_at > datetime.now(UTC),
    )
    row = db.execute(stmt).scalar_one_or_none()
    return password_reset_serializers.to_state(row) if row else None


def claim_password_reset_token(token_hash: str, db: Session) -> int | None:
    """Stage an atomic claim and return the owning user id when the token is valid."""
    stmt = (
        sa_update(password_reset_models.PasswordResetToken)
        .where(
            password_reset_models.PasswordResetToken.token_hash == token_hash,
            password_reset_models.PasswordResetToken.used.is_(False),
            password_reset_models.PasswordResetToken.expires_at > datetime.now(UTC),
        )
        .values(used=True)
        .returning(password_reset_models.PasswordResetToken.user_id)
    )
    user_id = db.execute(stmt).scalar_one_or_none()
    db.flush()
    return user_id


def mark_user_password_reset_tokens_used(user_id: int, db: Session) -> int:
    """Stage invalidation of all unused reset tokens for a user."""
    stmt = (
        sa_update(password_reset_models.PasswordResetToken)
        .where(
            password_reset_models.PasswordResetToken.user_id == user_id,
            password_reset_models.PasswordResetToken.used.is_(False),
        )
        .values(used=True)
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount or 0


def mark_password_reset_token_used(
    token_id: str, db: Session
) -> password_reset_contracts.PasswordResetTokenState | None:
    """Stage consumption of a token by its id and return its updated state."""
    stmt = select(password_reset_models.PasswordResetToken).where(
        password_reset_models.PasswordResetToken.id == token_id
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        return None
    row.used = True
    db.flush()
    return password_reset_serializers.to_state(row)


def delete_expired_password_reset_tokens(db: Session) -> int:
    """Stage deletion of expired reset tokens and return the affected row count."""
    stmt = sa_delete(password_reset_models.PasswordResetToken).where(
        password_reset_models.PasswordResetToken.expires_at < datetime.now(UTC)
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount or 0
