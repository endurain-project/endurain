"""Scheduled prune of devices no sign-in has used for the retention period."""

from datetime import UTC, datetime

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.known_devices.service as known_devices_service

logger = core_logger.get_logger(__name__)

PRUNE_LOCK_NAME = "auth_known_devices_prune"


def delete_unseen_devices() -> None:
    """Delete devices last seen longer ago than the retention period, one bounded batch per transaction."""
    with core_database.SessionLocal() as db:
        deleted_count = known_devices_service.delete_unseen_devices(datetime.now(UTC), db)
    if deleted_count:
        logger.info("Pruned devices unseen for the retention period", extra=core_logger.context(count=deleted_count))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring known-device maintenance work."""
    return (
        core_scheduler.ScheduledJob(
            delete_unseen_devices,
            1440,
            "prune devices unseen for 400 days",
            lock_name=PRUNE_LOCK_NAME,
        ),
    )
