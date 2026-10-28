"""Scheduled cleanup for rotated refresh-token records."""

from datetime import UTC, datetime, timedelta

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.rotated_refresh_tokens.service as rotated_token_service

logger = core_logger.get_logger(__name__)

ROTATED_TOKEN_CLEANUP_BUFFER_SECONDS = 10


def cleanup_expired_rotated_tokens() -> None:
    """Delete expired rotated-token rows in a short-lived transaction."""
    with core_database.SessionLocal() as db:
        cutoff = datetime.now(UTC) - timedelta(seconds=ROTATED_TOKEN_CLEANUP_BUFFER_SECONDS)
        deleted_count = rotated_token_service.delete_expired_tokens(cutoff, db)
        db.commit()
    if deleted_count:
        logger.info("Cleaned up expired rotated refresh-token records", extra=core_logger.context(count=deleted_count))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring rotated-token maintenance work."""
    return (
        core_scheduler.ScheduledJob(
            cleanup_expired_rotated_tokens,
            1,
            "cleanup expired rotated refresh tokens",
        ),
    )
