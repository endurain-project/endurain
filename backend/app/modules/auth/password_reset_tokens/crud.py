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


def password_reset_token_exists(token_hash: str, db: Session) -> bool:
    """Return whether a token with this hash was ever stored, used or not."""
    stmt = select(password_reset_models.PasswordResetToken.id).where(
        password_reset_models.PasswordResetToken.token_hash == token_hash
    )
    return db.execute(stmt).first() is not None


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


def delete_expired_password_reset_tokens(now: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` reset tokens that expired before ``now`` and return the row count."""
    model = password_reset_models.PasswordResetToken
    expired = select(model.id).where(model.expires_at < now).limit(limit)
    result = db.execute(sa_delete(model).where(model.id.in_(expired)))
    db.flush()
    return result.rowcount or 0
