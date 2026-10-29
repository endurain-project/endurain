"""Scheduled auth-session cleanup."""

import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.sessions.service as sessions_service
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)

CLEANUP_LOCK_NAME = "auth_sessions_idle_cleanup"


def delete_idle_sessions() -> None:
    """Delete idle sessions in a short-lived database session."""
    with SessionLocal() as db:
        deleted_count = sessions_service.delete_idle_sessions(db)
        db.commit()
    if deleted_count:
        logger.info("Deleted idle sessions", extra=core_logger.context(count=deleted_count))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring session maintenance work."""
    return (
        core_scheduler.ScheduledJob(
            delete_idle_sessions,
            15,
            "clean up idle auth sessions",
            lock_name=CLEANUP_LOCK_NAME,
        ),
    )
