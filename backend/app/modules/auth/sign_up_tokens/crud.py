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


def claim_sign_up_token(token_hash: str, db: Session) -> int | None:
    """Stage an atomic claim of an unused, unexpired token and return its user id.

    One conditional ``UPDATE`` flips ``used``, so of two requests presenting the same link only one
    matches a row.

    Args:
        token_hash: SHA-256 hash of the presented token.
        db: Database session.

    Returns:
        The user the token belongs to, or None when it is unknown, used or expired.
    """
    stmt = (
        sa_update(sign_up_models.SignUpToken)
        .where(
            sign_up_models.SignUpToken.token_hash == token_hash,
            sign_up_models.SignUpToken.used.is_(False),
            sign_up_models.SignUpToken.expires_at > datetime.now(UTC),
        )
        .values(used=True)
        .returning(sign_up_models.SignUpToken.user_id)
    )
    user_id = db.execute(stmt).scalar_one_or_none()
    db.flush()
    return user_id


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


def delete_expired_sign_up_tokens(now: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` sign-up tokens that expired before ``now`` and return the row count."""
    model = sign_up_models.SignUpToken
    expired = select(model.id).where(model.expires_at < now).limit(limit)
    result = db.execute(sa_delete(model).where(model.id.in_(expired)))
    db.flush()
    return result.rowcount or 0
