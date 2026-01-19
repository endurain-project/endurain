"""Utility functions for refresh token reuse detection."""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import auth.constants as auth_constants
import core.logger as core_logger
import users.users_session.crud as users_session_crud
import users.users_session.rotated_refresh_tokens.crud as rotated_token_crud
import users.users_session.rotated_refresh_tokens.schema as rotated_token_schema
from core.database import SessionLocal


# Grace period for token reuse (60 seconds)
# Allows for network retries/delays without false positives
TOKEN_REUSE_GRACE_PERIOD_SECONDS = 60


def hmac_hash_token(token: str) -> str:
    """
    Compute HMAC-SHA256 hash of a token for secure lookup.

    Uses the server's SECRET_KEY as the HMAC key, providing
    defense-in-depth: even if the database is compromised,
    an attacker cannot verify stolen tokens without the key.

    Args:
        token: The raw refresh token to hash.

    Returns:
        Hex-encoded HMAC-SHA256 hash of the token.
    """
    secret_key = auth_constants.JWT_SECRET_KEY
    if not secret_key:
        raise ValueError("JWT_SECRET_KEY is not configured")

    return hmac.new(secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


def store_rotated_token(
    raw_token: str,
    token_family_id: str,
    rotation_count: int,
    db: Session,
) -> None:
    """
    Store an old refresh token after rotation for reuse detection.

    Uses HMAC-SHA256 with the server secret to hash the token,
    enabling deterministic lookups while maintaining security.

    Args:
        raw_token: The raw refresh token being rotated out.
        token_family_id: UUID of the token family.
        rotation_count: Current rotation count for this token.
        db: Database session.

    Raises:
        HTTPException: If storage fails (500).
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=TOKEN_REUSE_GRACE_PERIOD_SECONDS)

    # Use HMAC-SHA256 for deterministic, secure hashing
    hashed_token = hmac_hash_token(raw_token)

    rotated_token = rotated_token_schema.RotatedRefreshTokenCreate(
        token_family_id=token_family_id,
        hashed_token=hashed_token,
        rotation_count=rotation_count,
        rotated_at=now,
        expires_at=expires_at,
    )

    rotated_token_crud.create_rotated_token(rotated_token, db)


def check_token_reuse(raw_token: str, db: Session) -> tuple[bool, bool]:
    """
    Check if a refresh token has been reused (already rotated).

    Uses HMAC-SHA256 with the server secret to hash the token
    for lookup, ensuring deterministic matching.

    Args:
        raw_token: The raw refresh token to check.
        db: Database session.

    Returns:
        Tuple of (is_reused, in_grace_period):
        - (False, False): Token is valid, not reused
        - (True, True): Reused but within 60s grace period
        - (True, False): Reused after grace period - THEFT!

    Raises:
        HTTPException: If lookup fails (500).
    """
    # Use HMAC-SHA256 for deterministic lookup
    hashed_token = hmac_hash_token(raw_token)
    rotated_token = rotated_token_crud.get_rotated_token_by_hash(hashed_token, db)

    if not rotated_token:
        return (False, False)

    # Token was already rotated - check grace period
    now = datetime.now(timezone.utc)

    if now <= rotated_token.expires_at:
        # Within grace period - might be legitimate retry
        core_logger.print_to_log(
            f"Token reuse within grace period for family "
            f"{rotated_token.token_family_id}",
            "warning",
            context={
                "token_family_id": rotated_token.token_family_id,
                "rotation_count": rotated_token.rotation_count,
            },
        )
        return (True, True)

    # Past grace period - likely theft!
    core_logger.print_to_log(
        f"Token reuse detected after grace period for family "
        f"{rotated_token.token_family_id}",
        "error",
        context={
            "token_family_id": rotated_token.token_family_id,
            "rotation_count": rotated_token.rotation_count,
            "rotated_at": rotated_token.rotated_at.isoformat(),
        },
    )
    return (True, False)


def invalidate_token_family(token_family_id: str, db: Session) -> int:
    """
    Invalidate all sessions in a token family due to reuse detection.

    Args:
        token_family_id: The family ID to invalidate.
        db: Database session.

    Returns:
        Number of sessions invalidated.

    Raises:
        HTTPException: If invalidation fails (500).
    """
    # Delete all sessions in the family
    num_sessions_deleted = users_session_crud.delete_sessions_by_family(
        token_family_id, db
    )

    # Delete all rotated tokens for this family
    num_tokens_deleted = rotated_token_crud.delete_by_family(token_family_id, db)

    core_logger.print_to_log(
        f"Invalidated token family {token_family_id} due to reuse: "
        f"{num_sessions_deleted} sessions, {num_tokens_deleted} tokens",
        "error",
        context={
            "token_family_id": token_family_id,
            "sessions_deleted": num_sessions_deleted,
            "tokens_deleted": num_tokens_deleted,
        },
    )

    return num_sessions_deleted


def cleanup_expired_rotated_tokens() -> None:
    """
    Cleanup job to delete expired rotated tokens.

    This function is called by the scheduler to periodically remove
    tokens that have exceeded the grace period. Should run every 5
    minutes.

    Raises:
        Any exceptions are caught, logged, and not propagated to avoid
        breaking the scheduler.
    """
    db = SessionLocal()
    try:
        cutoff_time = datetime.now(timezone.utc)
        deleted_count = rotated_token_crud.delete_expired_tokens(cutoff_time, db)

        if deleted_count > 0:
            core_logger.print_to_log(
                f"Cleaned up {deleted_count} expired rotated tokens",
                "info",
            )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in cleanup_expired_rotated_tokens: {err}",
            "error",
            exc=err,
        )
    finally:
        db.close()
