"""Persistence operations for sign-up tokens."""

from collections.abc import Collection
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.auth.sign_up_tokens.serializers as sign_up_serializers


def claim_sign_up_token(token_hash: str, db: Session) -> sign_up_contracts.SignUpTokenClaim | None:
    """Stage an atomic claim of an unused, unexpired token and return what it proves.

    One conditional ``UPDATE`` flips ``used``, so of two requests presenting the same link only one
    matches a row.

    Args:
        token_hash: SHA-256 hash of the presented token.
        db: Database session.

    Returns:
        The claimed token's id, user and addresses, or None when it is unknown, used or expired.
    """
    model = sign_up_models.SignUpToken
    stmt = (
        sa_update(model)
        .where(
            model.token_hash == token_hash,
            model.used.is_(False),
            model.expires_at > datetime.now(UTC),
        )
        .values(used=True)
        .returning(model.id, model.user_id, model.email, model.previous_email)
    )
    row = db.execute(stmt).one_or_none()
    db.flush()
    return sign_up_serializers.to_claim(row) if row is not None else None


def get_pending_email_change_tokens(
    user_ids: Collection[int], now: datetime, db: Session
) -> list[sign_up_contracts.SignUpTokenState]:
    """Return the unused, unexpired email-change tokens of the given users.

    Args:
        user_ids: The users to look up.
        now: The instant a token must still be valid at.
        db: Database session.

    Returns:
        The users' pending email-change tokens.
    """
    model = sign_up_models.SignUpToken
    stmt = select(model).where(
        model.user_id.in_(user_ids),
        model.used.is_(False),
        model.expires_at > now,
        model.previous_email.is_not(None),
    )
    return [sign_up_serializers.to_state(row) for row in db.execute(stmt).scalars().all()]


def get_sign_up_token_by_id(token_id: str, db: Session) -> sign_up_contracts.SignUpTokenState | None:
    """Return a token by id, whether or not it has been used, or None when there is none."""
    row = db.get(sign_up_models.SignUpToken, token_id)
    return sign_up_serializers.to_state(row) if row is not None else None


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
        email=token.email,
        previous_email=token.previous_email,
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
