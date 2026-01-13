from datetime import datetime, timezone

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

import auth.idp_link_tokens.models as idp_link_token_models
import auth.idp_link_tokens.schema as idp_link_token_schema

import core.logger as core_logger


def get_idp_link_token_by_id(
    token_id: str, db: Session
) -> idp_link_token_models.IdpLinkToken | None:
    """
    Retrieve an IdP link token by ID, validate not expired/used.

    Args:
        token_id: The token ID to lookup.
        db: Database session.

    Returns:
        IdpLinkToken if valid and not expired/used, else None.
    """
    try:
        token = (
            db.query(idp_link_token_models.IdpLinkToken)
            .filter(idp_link_token_models.IdpLinkToken.id == token_id)
            .first()
        )

        if not token:
            core_logger.print_to_log(
                f"IdP link token not found: {token_id[:8]}...", "warning"
            )
            return None

        # Check expiry
        if datetime.now(timezone.utc) > token.expires_at.replace(tzinfo=timezone.utc):
            core_logger.print_to_log(
                f"IdP link token expired: {token_id[:8]}...", "warning"
            )
            return None

        # Check if already used
        if token.used:
            core_logger.print_to_log(
                f"IdP link token already used (replay attempt?): {token_id[:8]}...",
                "warning",
            )
            return None

        return token
    except Exception as err:
        core_logger.print_to_log(
            f"Error retrieving IdP link token: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve link token",
        ) from err


def create_idp_link_token(
    token_data: idp_link_token_schema.IdpLinkTokenCreate, db: Session
) -> idp_link_token_models.IdpLinkToken:
    """
    Create and persist an IdP link token in the database.

    Args:
        token_data: Schema object containing token data.
        db: Database session.

    Returns:
        The persisted IdpLinkToken instance.

    Raises:
        HTTPException: If token creation fails.
    """
    try:
        db_token = idp_link_token_models.IdpLinkToken(**token_data.model_dump())
        db.add(db_token)
        db.commit()
        db.refresh(db_token)
        return db_token
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error creating IdP link token: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create link token",
        ) from err


def mark_token_as_used(token_id: str, db: Session) -> None:
    """
    Mark an IdP link token as used to prevent replay attacks.

    Args:
        token_id: The token ID to mark as used.
        db: Database session.

    Raises:
        HTTPException: If the update fails.
    """
    try:
        token = (
            db.query(idp_link_token_models.IdpLinkToken)
            .filter(idp_link_token_models.IdpLinkToken.id == token_id)
            .first()
        )

        if token:
            token.used = True
            db.commit()
            core_logger.print_to_log(
                f"IdP link token marked as used: {token_id[:8]}...", "debug"
            )
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error marking IdP link token as used: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark token as used",
        ) from err


def delete_expired_tokens(db: Session) -> int:
    """
    Delete all expired IdP link tokens from the database.

    Args:
        db: Database session.

    Returns:
        Number of tokens deleted.
    """
    try:
        current_time = datetime.now(timezone.utc)
        deleted_count = (
            db.query(idp_link_token_models.IdpLinkToken)
            .filter(idp_link_token_models.IdpLinkToken.expires_at < current_time)
            .delete()
        )
        db.commit()

        if deleted_count > 0:
            core_logger.print_to_log(
                f"Deleted {deleted_count} expired IdP link token(s)", "debug"
            )

        return deleted_count
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error deleting expired IdP link tokens: {err}", "error", exc=err
        )
        return 0
