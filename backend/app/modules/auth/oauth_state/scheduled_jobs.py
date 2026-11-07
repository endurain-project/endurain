"""Scheduled OAuth-state cleanup."""

import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.oauth_state.service as oauth_state_service
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)

PURGE_LOCK_NAME = "auth_oauth_state_purge"


def delete_expired_oauth_states_from_db() -> None:
    """Delete expired OAuth states, one bounded batch per transaction."""
    with SessionLocal() as db:
        deleted_count = oauth_state_service.delete_expired_oauth_states(db)
    if deleted_count:
        logger.info("Deleted expired OAuth states", extra=core_logger.context(count=deleted_count))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring OAuth-state maintenance work."""
    return (
        core_scheduler.ScheduledJob(
            delete_expired_oauth_states_from_db,
            5,
            "delete expired OAuth states from the database",
            lock_name=PURGE_LOCK_NAME,
        ),
    )
