"""Recurring maintenance for API keys."""

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.api_keys.service as api_keys_service

logger = core_logger.get_logger(__name__)

PURGE_LOCK_NAME = "auth_api_keys_purge"


def delete_stale_api_keys_from_db() -> None:
    """Delete the API keys revoked or expired longer ago than the retention, one bounded batch per transaction."""
    with core_database.SessionLocal() as db:
        deleted_count = api_keys_service.delete_stale_api_keys(db)
    if deleted_count:
        logger.info("Deleted stale API keys", extra=core_logger.context(count=deleted_count))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring API-key cleanup work."""
    return (
        core_scheduler.ScheduledJob(
            delete_stale_api_keys_from_db,
            60,
            "delete API keys revoked or expired long ago from the database",
            lock_name=PURGE_LOCK_NAME,
        ),
    )
