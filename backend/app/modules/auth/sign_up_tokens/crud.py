"""Persistence operations for sign-up tokens."""

import uuid
from collections.abc import Collection
from datetime import UTC, datetime

from sqlalchemy import Select, or_, select
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.auth.sign_up_tokens.serializers as sign_up_serializers


def get_usable_sign_up_token(token_hash: str, db: Session) -> sign_up_contracts.SignUpTokenClaim | None:
    """Return what an unused, unexpired token proves, without consuming it.

    Args:
        token_hash: SHA-256 hash of the presented token.
        db: Database session.

    Returns:
        The token's id, user and addresses, or None when it is unknown, used or expired.
    """
    model = sign_up_models.SignUpToken
    stmt = select(model.id, model.user_id, model.email, model.previous_email, model.security_generation).where(
        model.token_hash == token_hash,
        model.used.is_(False),
        model.expires_at > datetime.now(UTC),
    )
    row = db.execute(stmt).one_or_none()
    return sign_up_serializers.to_claim(row) if row is not None else None


def claim_sign_up_token(token_hash: str, db: Session) -> sign_up_contracts.SignUpTokenClaim | None:
    """Stage an atomic claim of an unused, unexpired token and return what it proves.

    One conditional ``UPDATE`` flips ``used`` and records the confirmation, so of two requests presenting the same link only one
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
        .values(used=True, confirmed_at=datetime.now(UTC))
        .returning(model.id, model.user_id, model.email, model.previous_email, model.security_generation)
    )
    row = db.execute(stmt).one_or_none()
    db.flush()
    return sign_up_serializers.to_claim(row) if row is not None else None


def get_pending_email_change_tokens(
    user_ids: Collection[uuid.UUID], now: datetime, db: Session
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


def get_email_change_tokens(change_id: str, now: datetime, db: Session) -> list[sign_up_contracts.SignUpTokenState]:
    """Return the rows of an email change whose revert window is still open.

    Args:
        change_id: The identifier of the change.
        now: The instant the revert window must still be open at.
        db: Database session.

    Returns:
        Every row of the change, the confirmation links that were mailed for it among them; empty when the change is
        unknown or its window has closed.
    """
    model = sign_up_models.SignUpToken
    stmt = select(model).where(model.change_id == change_id, model.revert_until > now)
    return [sign_up_serializers.to_state(row) for row in db.execute(stmt).scalars().all()]


def get_later_email_change_ids(
    user_id: uuid.UUID, change_id: str, since: datetime, now: datetime, db: Session
) -> list[str]:
    """Return the other email changes of the user that began after ``since`` and can still be reverted.

    Args:
        user_id: The user to look up.
        change_id: The identifier of the change to compare against.
        since: The instant the change began.
        now: The instant a change's revert window must still be open at.
        db: Database session.

    Returns:
        The identifiers of the different changes that have a row created after ``since``, a revert window still open
        and no revert yet.
    """
    model = sign_up_models.SignUpToken
    stmt = select(model.change_id).where(
        model.user_id == user_id,
        model.change_id.is_not(None),
        model.change_id != change_id,
        model.created_at > since,
        model.revert_until > now,
        model.reverted_at.is_(None),
    )
    return sorted({row for row in db.execute(stmt).scalars().all() if row is not None})


def mark_email_changes_reverted(change_ids: Collection[str], db: Session) -> int:
    """Stage the revert of email changes, once each, and return how many rows it marked.

    One conditional ``UPDATE`` sets ``reverted_at``, so of two requests presenting the same link only one matches rows.

    Args:
        change_ids: The identifiers of the changes.
        db: Database session.

    Returns:
        The number of rows marked; zero when the changes were already reverted.
    """
    model = sign_up_models.SignUpToken
    stmt = (
        sa_update(model)
        .where(model.change_id.in_(change_ids), model.reverted_at.is_(None))
        .values(reverted_at=datetime.now(UTC))
    )
    matched = core_database.rowcount(db, stmt)
    db.flush()
    return matched


def get_email_reserver_id(email: str, except_user_id: uuid.UUID | None, now: datetime, db: Session) -> uuid.UUID | None:
    """Return the user whose confirmed email change left ``email`` behind and can still be reverted.

    Args:
        email: The address, in any case.
        except_user_id: A user who does not count as the reserver, or None for every user.
        now: The instant the revert window must still be open at.
        db: Database session.

    Returns:
        The user whose change has ``email`` as its previous address, a revert window still open and no revert yet, or
        None when no other user reserves it.
    """
    model = sign_up_models.SignUpToken
    stmt = (
        select(model.user_id)
        .where(
            model.previous_email == email.lower(),
            model.confirmed_at.is_not(None),
            model.reverted_at.is_(None),
            model.revert_until > now,
        )
        .order_by(model.user_id)
        .limit(1)
    )
    if except_user_id is not None:
        stmt = stmt.where(model.user_id != except_user_id)
    return db.execute(stmt).scalar_one_or_none()


def get_sign_up_token_by_id(token_id: str, db: Session) -> sign_up_contracts.SignUpTokenState | None:
    """Return a token by id, whether or not it has been used, or None when there is none."""
    row = db.get(sign_up_models.SignUpToken, token_id)
    return sign_up_serializers.to_state(row) if row is not None else None


def sign_up_token_exists(token_hash: str, db: Session) -> bool:
    """Return whether a token with this hash was ever stored, used or not."""
    stmt = select(sign_up_models.SignUpToken.id).where(sign_up_models.SignUpToken.token_hash == token_hash)
    return db.execute(stmt).first() is not None


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
        security_generation=token.security_generation,
        change_id=token.change_id,
        revert_until=token.revert_until,
        confirmed_at=token.confirmed_at,
    )
    db.add(row)
    db.flush()
    return sign_up_serializers.to_state(row)


def mark_user_sign_up_tokens_used(user_id: uuid.UUID, db: Session) -> int:
    """Stage invalidation of all unused sign-up tokens for a user."""
    stmt = (
        sa_update(sign_up_models.SignUpToken)
        .where(sign_up_models.SignUpToken.user_id == user_id, sign_up_models.SignUpToken.used.is_(False))
        .values(used=True)
    )
    matched = core_database.rowcount(db, stmt)
    db.flush()
    return matched


def delete_expired_sign_up_tokens(now: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` expired sign-up tokens and return the row count.

    An email-change row is kept until its revert window closes, so its "this wasn't me" link keeps working after
    the confirmation link expired.
    """
    model = sign_up_models.SignUpToken
    expired = (
        select(model.id)
        .where(model.expires_at < now, or_(model.revert_until.is_(None), model.revert_until < now))
        .limit(limit)
    )
    matched = core_database.rowcount(db, sa_delete(model).where(model.id.in_(expired)))
    db.flush()
    return matched


def select_users_with_live_token_ids(now: datetime) -> Select[tuple[uuid.UUID]]:
    """Return a query for the ids of the users who hold a token that is unused and unexpired at ``now``.

    Args:
        now: The instant a token must still be valid at.

    Returns:
        A select of user ids, for a caller to use in an ``IN`` or ``NOT IN``.
    """
    model = sign_up_models.SignUpToken
    return select(model.user_id).where(model.used.is_(False), model.expires_at > now)
