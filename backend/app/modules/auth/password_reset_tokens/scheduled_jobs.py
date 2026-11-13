"""Recurring maintenance for password reset tokens."""

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.password_reset_tokens.service as password_reset_service

logger = core_logger.get_logger(__name__)

PURGE_LOCK_NAME = "auth_password_reset_tokens_purge"


def delete_expired_tokens_from_db() -> None:
    """Delete expired reset tokens, one bounded batch per transaction."""
    with core_database.SessionLocal() as db:
        deleted_count = password_reset_service.delete_expired_password_reset_tokens(db)
    if deleted_count:
        logger.info("Deleted expired password reset tokens", extra=core_logger.context(count=deleted_count))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring password-reset-token cleanup work."""
    return (
        core_scheduler.ScheduledJob(
            delete_expired_tokens_from_db,
            60,
            "delete invalid password reset tokens from the database",
            lock_name=PURGE_LOCK_NAME,
        ),
    )
