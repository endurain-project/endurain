"""Migration 14: clear the shared state, whose keys embed integer user ids."""

import jasil.runtime as platform_runtime
from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.service as migrations_service

logger = core_logger.get_logger(__name__)

#: The state namespace this migration clears: the attempt, cooldown, job, ticket and per-user stores keyed under it.
#: The provider rate-limit flags, the Strava token refresh claim and the limiter counters sit outside it and expire on
#: their own TTL.
_STATE_NAMESPACE = "endurain:"


def process_migration_14(db: Session) -> None:
    """Clear the ``endurain:`` state namespace once and mark the migration executed.

    The keys of the namespace embed integer user ids, so none of them can name an account any more (this also lifts
    every account lockout). The migration is marked executed right after the clear, so no later start clears the
    state the application wrote after the upgrade. A failure is logged and leaves the migration pending, so the next
    start retries the clear.

    Args:
        db: The SQLAlchemy database session.
    """
    logger.info("Started migration 14", extra=core_logger.context(console=True))

    try:
        platform_runtime.get_active_platform().state.delete_prefix(_STATE_NAMESPACE)
    except Exception as err:
        logger.error(
            f"Migration 14 - could not clear the state: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        return

    try:
        migrations_service.mark_executed(14, db)
    except Exception as err:
        db.rollback()
        logger.error(
            f"Migration 14 - failed to set migration as executed: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        return

    logger.info("Finished migration 14", extra=core_logger.context(console=True))
