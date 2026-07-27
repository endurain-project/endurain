"""CRUD operations for IdP link tokens."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CursorResult, select
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.auth.identity_providers.link_tokens.models as idp_link_token_models
import modules.auth.identity_providers.link_tokens.schema as idp_link_token_schema

logger = core_logger.get_logger(__name__)


@core_decorators.handle_db_errors
def get_idp_link_token_by_hash(token_hash: str, db: Session) -> idp_link_token_models.IdpLinkToken | None:
    """Retrieve a valid IdP link token by token hash.

    Args:
        token_hash: SHA-256 hash of the plaintext link token.
        db: SQLAlchemy database session.

    Returns:
        The matching IdpLinkToken if valid (not expired and unused),
        None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(idp_link_token_models.IdpLinkToken).where(
        idp_link_token_models.IdpLinkToken.token_hash == token_hash,
        idp_link_token_models.IdpLinkToken.used.is_(False),
        idp_link_token_models.IdpLinkToken.expires_at > datetime.now(UTC),
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def create_idp_link_token(
    token_data: idp_link_token_schema.IdpLinkTokenCreate, db: Session
) -> idp_link_token_models.IdpLinkToken:
    """Create and persist an IdP link token in the database.

    Args:
        token_data: Schema object containing token data.
        db: SQLAlchemy database session.

    Returns:
        The persisted IdpLinkToken instance.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    db_token = idp_link_token_models.IdpLinkToken(**token_data.model_dump())
    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token


@core_decorators.handle_db_errors
def mark_token_as_used(token_hash: str, db: Session) -> bool:
    """Atomically mark an unused, unexpired IdP link token as used.

    Performs a single conditional UPDATE so concurrent attempts to
    consume the same token cannot both succeed (replay protection).

    Args:
        token_hash: SHA-256 hash of the plaintext link token.
        db: SQLAlchemy database session.

    Returns:
        True if exactly one row was claimed, False if the token was
        missing, expired, or already consumed.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    stmt = (
        sa_update(idp_link_token_models.IdpLinkToken)
        .where(
            idp_link_token_models.IdpLinkToken.token_hash == token_hash,
            idp_link_token_models.IdpLinkToken.used.is_(False),
            idp_link_token_models.IdpLinkToken.expires_at > datetime.now(UTC),
        )
        .values(used=True)
    )
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()

    claimed = result.rowcount == 1
    if claimed:
        logger.debug("IdP link token marked as used")
    return claimed


@core_decorators.handle_db_errors
def delete_expired_tokens(db: Session) -> int:
    """Delete all expired IdP link tokens from the database.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Number of tokens deleted.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    stmt = sa_delete(idp_link_token_models.IdpLinkToken).where(
        idp_link_token_models.IdpLinkToken.expires_at < datetime.now(UTC)
    )
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()

    deleted_count = result.rowcount
    if deleted_count > 0:
        logger.debug(f"Deleted {deleted_count} expired IdP link token(s)")
    return deleted_count
