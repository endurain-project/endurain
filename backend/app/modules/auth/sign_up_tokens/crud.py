"""Persistence operations for sign-up tokens."""

from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.auth.sign_up_tokens.serializers as sign_up_serializers


def get_sign_up_token_by_hash(token_hash: str, db: Session) -> sign_up_contracts.SignUpTokenState | None:
    """Return an unused, unexpired token state matching the hash."""
    stmt = select(sign_up_models.SignUpToken).where(
        sign_up_models.SignUpToken.token_hash == token_hash,
        sign_up_models.SignUpToken.used.is_(False),
        sign_up_models.SignUpToken.expires_at > datetime.now(UTC),
    )
    row = db.execute(stmt).scalar_one_or_none()
    return sign_up_serializers.to_state(row) if row else None


def create_sign_up_token(
    token: sign_up_schema.SignUpToken,
    db: Session,
) -> sign_up_contracts.SignUpTokenState:
    """Stage a token row and return its internal state."""
    row = sign_up_models.SignUpToken(
        id=token.id,
        user_id=token.user_id,
        token_hash=token.token_hash,
        created_at=token.created_at,
        expires_at=token.expires_at,
        used=token.used,
    )
    db.add(row)
    db.flush()
    return sign_up_serializers.to_state(row)


def mark_user_sign_up_tokens_used(user_id: int, db: Session) -> int:
    """Stage invalidation of all unused sign-up tokens for a user."""
    stmt = (
        sa_update(sign_up_models.SignUpToken)
        .where(sign_up_models.SignUpToken.user_id == user_id, sign_up_models.SignUpToken.used.is_(False))
        .values(used=True)
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount or 0


def mark_sign_up_token_used(token_id: str, db: Session) -> sign_up_contracts.SignUpTokenState | None:
    """Stage consumption of a token by its id and return its updated state."""
    stmt = select(sign_up_models.SignUpToken).where(sign_up_models.SignUpToken.id == token_id)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        return None
    row.used = True
    db.flush()
    return sign_up_serializers.to_state(row)


def delete_expired_sign_up_tokens(db: Session) -> int:
    """Stage deletion of expired sign-up tokens and return the affected row count."""
    stmt = sa_delete(sign_up_models.SignUpToken).where(sign_up_models.SignUpToken.expires_at < datetime.now(UTC))
    result = db.execute(stmt)
    db.flush()
    return result.rowcount or 0
