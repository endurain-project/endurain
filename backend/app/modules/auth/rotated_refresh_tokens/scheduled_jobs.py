"""Scheduled cleanup for rotated refresh-token records."""

from datetime import UTC, datetime

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.rotated_refresh_tokens.service as rotated_token_service

logger = core_logger.get_logger(__name__)

CLEANUP_LOCK_NAME = "auth_rotated_refresh_tokens_cleanup"


def delete_expired_rotated_tokens() -> None:
    """Delete rotated-token rows whose refresh token has expired, one bounded batch per transaction.

    A rotated token stays recorded until it could no longer be presented, so a replay after the grace
    window is still recognised as reuse. Each row carries its own token's expiry, so a change to the
    refresh-token lifetime neither drops a record early nor keeps one past its token.
    """
    with core_database.SessionLocal() as db:
        deleted_count = rotated_token_service.delete_expired_tokens(datetime.now(UTC), db)
    if deleted_count:
        logger.info("Cleaned up expired rotated refresh-token records", extra=core_logger.context(count=deleted_count))


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
