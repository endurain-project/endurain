"""Scheduled cleanup for rotated refresh-token records."""

from datetime import UTC, datetime

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.rotated_refresh_tokens.service as rotated_token_service

logger = core_logger.get_logger(__name__)

CLEANUP_LOCK_NAME = "auth_rotated_refresh_tokens_cleanup"
REENCRYPT_LOCK_NAME = "auth_rotated_refresh_tokens_reencrypt"


def delete_expired_rotated_tokens() -> None:
    """Clear ended grace windows' replacement tokens and delete expired rotated-token rows, in bounded batches.

    A replacement token is needed only inside the grace window, so it is cleared once that has ended; the
    record stays for reuse detection.

    A rotated token stays recorded until it could no longer be presented, so a replay after the grace
    window is still recognised as reuse. Each row carries its own token's expiry, so a change to the
    refresh-token lifetime neither drops a record early nor keeps one past its token.
    """
    now = datetime.now(UTC)
    with core_database.SessionLocal() as db:
        rotated_token_service.clear_expired_replacements(now, db)
        deleted_count = rotated_token_service.delete_expired_tokens(now, db)
    if deleted_count:
        logger.info("Cleaned up expired rotated refresh-token records", extra=core_logger.context(count=deleted_count))


def reencrypt_stored_secrets() -> None:
    """Re-encrypt the stored replacement tokens under the first FERNET_KEY; does nothing while one key is configured."""
    with core_database.SessionLocal() as db:
        rotated_token_service.reencrypt_stored_secrets(db)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring rotated-token maintenance work."""
    return (
        core_scheduler.ScheduledJob(
            delete_expired_rotated_tokens,
            1,
            "cleanup expired rotated refresh tokens",
            lock_name=CLEANUP_LOCK_NAME,
        ),
    )
