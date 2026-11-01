"""Recurring maintenance for sign-up tokens."""

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.sign_up_tokens.service as sign_up_service

logger = core_logger.get_logger(__name__)

PURGE_LOCK_NAME = "auth_sign_up_tokens_purge"


def delete_expired_tokens_from_db() -> None:
    """Delete expired sign-up tokens, one bounded batch per transaction."""
    with core_database.SessionLocal() as db:
        deleted_count = sign_up_service.delete_expired_sign_up_tokens(db)
    if deleted_count:
        logger.info("Deleted expired sign-up tokens", extra=core_logger.context(count=deleted_count))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring sign-up-token cleanup work."""
    return (
        core_scheduler.ScheduledJob(
            delete_expired_tokens_from_db,
            60,
            "delete invalid sign-up tokens from the database",
            lock_name=PURGE_LOCK_NAME,
        ),
    )
