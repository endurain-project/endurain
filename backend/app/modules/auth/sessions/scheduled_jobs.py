"""Scheduled auth-session cleanup."""

import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.sessions.service as sessions_service
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)

CLEANUP_LOCK_NAME = "auth_sessions_cleanup"


def delete_stale_sessions() -> None:
    """Delete expired sessions, then idle ones, one bounded batch per transaction."""
    with SessionLocal() as db:
        expired_count = sessions_service.delete_expired_sessions(db)
        idle_count = sessions_service.delete_idle_sessions(db)
    if expired_count or idle_count:
        logger.info("Deleted stale sessions", extra=core_logger.context(expired=expired_count, idle=idle_count))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring session maintenance work."""
    return (
        core_scheduler.ScheduledJob(
            delete_stale_sessions,
            15,
            "clean up expired and idle auth sessions",
            lock_name=CLEANUP_LOCK_NAME,
        ),
    )
