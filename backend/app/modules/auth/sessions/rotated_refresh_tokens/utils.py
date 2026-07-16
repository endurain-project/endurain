"""Utility functions for refresh token reuse detection."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.logger as core_logger
import modules.auth.sessions.crud as auth_sessions_crud
import modules.auth.sessions.rotated_refresh_tokens.crud as rotated_token_crud
import modules.auth.sessions.rotated_refresh_tokens.schema as rotated_token_schema
import modules.auth.token_hashing as token_hashing
from core.database import SessionLocal

# Grace period for token reuse (60 seconds)
# Allows for network retries/delays without false positives
TOKEN_REUSE_GRACE_PERIOD_SECONDS: int = 60

# Extra seconds a rotated record is retained beyond its grace window before the
# cleanup job removes it. Keeping the row a little longer than
# TOKEN_REUSE_GRACE_PERIOD_SECONDS guarantees that an in-grace retry landing near
# the boundary always finds its record (so it can be replayed) and that reuse
# just past the window is still detected as theft instead of silently becoming a
# plain "invalid token" because cleanup raced the boundary.
ROTATED_TOKEN_CLEANUP_BUFFER_SECONDS: int = 10


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

    Raises:
        ValueError: If JWT_SECRET_KEY is not configured.
    """
    return token_hashing.hmac_sha256(token)


def store_rotated_token(
    raw_token: str,
    token_family_id: str,
    rotation_count: int,
    db: Session,
    *,
    replacement_refresh_token: str,
    replacement_refresh_token_exp: datetime,
) -> None:
    """
    Store an old refresh token after rotation for reuse detection.

    Uses HMAC-SHA256 with the server secret to hash the rotated
    token for deterministic lookups, and stores the replacement
    refresh token encrypted at rest so a legitimate retry inside
    the grace window can be replayed idempotently.

    Args:
        raw_token: The raw refresh token being rotated out.
        token_family_id: UUID of the token family.
        rotation_count: Current rotation count for this token.
        db: SQLAlchemy database session.
        replacement_refresh_token: The new refresh token minted
            to replace ``raw_token`` (replayed within grace).
        replacement_refresh_token_exp: Expiry of the replacement
            refresh token.

    Raises:
        HTTPException: If storage fails.
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=TOKEN_REUSE_GRACE_PERIOD_SECONDS)

    # Use HMAC-SHA256 for deterministic, secure hashing
    hashed_token = hmac_hash_token(raw_token)

    rotated_token = rotated_token_schema.RotatedRefreshTokenCreate(
        token_family_id=token_family_id,
        hashed_token=hashed_token,
        rotation_count=rotation_count,
        rotated_at=now,
        expires_at=expires_at,
        replacement_refresh_token=core_cryptography.encrypt_token_fernet(replacement_refresh_token),
        replacement_refresh_token_exp=replacement_refresh_token_exp,
    )

    rotated_token_crud.create_rotated_token(rotated_token, db)


def check_token_reuse(raw_token: str, db: Session) -> tuple[bool, bool]:
    """
    Check if a refresh token has been reused (already rotated).

    Uses HMAC-SHA256 with the server secret to hash the token
    for lookup, ensuring deterministic matching.

    Args:
        raw_token: The raw refresh token to check.
        db: SQLAlchemy database session.

    Returns:
        Tuple of (is_reused, in_grace_period):
            - (False, False): Token is valid, not reused.
            - (True, True): Reused but within 60s grace period.
            - (True, False): Reused after grace period - THEFT!

    Raises:
        HTTPException: If lookup fails.
    """
    # Use HMAC-SHA256 for deterministic lookup
    hashed_token = hmac_hash_token(raw_token)
    rotated_token = rotated_token_crud.get_rotated_token_by_hash(hashed_token, db)

    if not rotated_token:
        return (False, False)

    # Token was already rotated - check grace period
    now = datetime.now(UTC)

    if now <= rotated_token.expires_at:
        # Within grace period - might be legitimate retry
        core_logger.print_to_log(
            f"Token reuse within grace period for family {rotated_token.token_family_id}",
            "warning",
            context={
                "token_family_id": rotated_token.token_family_id,
                "rotation_count": rotated_token.rotation_count,
            },
        )
        return (True, True)

    # Past grace period - likely theft!
    core_logger.print_to_log(
        f"Token reuse detected after grace period for family {rotated_token.token_family_id}",
        "error",
        context={
            "token_family_id": rotated_token.token_family_id,
            "rotation_count": rotated_token.rotation_count,
            "rotated_at": rotated_token.rotated_at.isoformat(),
        },
    )
    return (True, False)


def get_grace_replay_token(raw_token: str, db: Session) -> tuple[str, datetime] | None:
    """
    Return the replacement refresh token for an in-grace retry.

    When a refresh token is presented again while still inside the
    grace window (a lost rotation response or a racing retry), the
    replacement minted on the original rotation is replayed instead
    of issuing a brand-new token, so duplicate/concurrent refreshes
    converge on a single outcome.

    Args:
        raw_token: The raw refresh token being replayed.
        db: SQLAlchemy database session.

    Returns:
        Tuple of (replacement_refresh_token, expiry) when a live
        in-grace record with a stored replacement exists, else None.

    Raises:
        HTTPException: If lookup or decryption fails.
    """
    hashed_token = hmac_hash_token(raw_token)
    rotated_token = rotated_token_crud.get_rotated_token_by_hash(hashed_token, db)

    if rotated_token is None:
        return None

    # Only replay inside the grace window; past it, reuse is theft.
    if datetime.now(UTC) > rotated_token.expires_at:
        return None

    if not rotated_token.replacement_refresh_token or rotated_token.replacement_refresh_token_exp is None:
        return None

    replacement = core_cryptography.decrypt_token_fernet(rotated_token.replacement_refresh_token)

    if replacement is None:
        return None

    return (replacement, rotated_token.replacement_refresh_token_exp)


def invalidate_token_family(token_family_id: str, db: Session) -> int:
    """
    Invalidate all sessions in a token family due to reuse detection.

    Args:
        token_family_id: The family ID to invalidate.
        db: SQLAlchemy database session.

    Returns:
        Number of sessions invalidated.

    Raises:
        HTTPException: If invalidation fails.
    """
    # Delete all sessions in the family
    num_sessions_deleted = auth_sessions_crud.delete_sessions_by_family(token_family_id, db)

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

    Called by the scheduler to periodically remove tokens that
    have exceeded the grace period. Should run every 1 minute.
    Exceptions are caught and logged to avoid breaking the
    scheduler.

    Returns:
        None.
    """
    with SessionLocal() as db:
        try:
            # Retain rotated records a few seconds past their grace window so a
            # boundary retry can still be replayed and post-grace reuse is still
            # caught as theft (see ROTATED_TOKEN_CLEANUP_BUFFER_SECONDS).
            cutoff_time = datetime.now(UTC) - timedelta(seconds=ROTATED_TOKEN_CLEANUP_BUFFER_SECONDS)
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
