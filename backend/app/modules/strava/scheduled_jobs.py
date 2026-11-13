"""The Strava module's scheduled work, declared by the module that owns it.

The hourly deletion of the Strava data of users who revoked Endurain's access on Strava and did not
relink within the grace period. Declared here so the composition root can collect it without
``core.scheduler`` importing a provider.
"""

import uuid

import sqlalchemy.exc

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.strava.constants as strava_constants
import modules.strava.service as strava_service

logger = core_logger.get_logger(__name__)

REVOKED_DATA_DELETE_LOCK = "strava_revoked_data_delete"

#: Minutes between runs of the revoked-access deletion.
REVOKED_DATA_DELETE_MINUTES = 60


def delete_revoked_data() -> None:
    """Delete the Strava data of every user whose revoked access is past the grace period.

    A user whose deletion fails is logged and left marked, so the next run tries again; it does not stop the
    users after them.
    """
    after_id: uuid.UUID | None = None
    while True:
        user_ids = strava_service.revoked_user_ids_due(after_id, strava_constants.REVOKED_DELETE_PAGE_SIZE)
        for user_id in user_ids:
            try:
                strava_service.delete_revoked_data(user_id)
            except (sqlalchemy.exc.SQLAlchemyError, core_exceptions.DomainError) as err:
                logger.error(
                    "Unable to delete the Strava data of a revoked account",
                    extra=core_logger.context(user_id=user_id),
                    exc_info=err,
                )
        if len(user_ids) < strava_constants.REVOKED_DELETE_PAGE_SIZE:
            return
        after_id = user_ids[-1]


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the Strava module's recurring scheduled jobs.

    Returns:
        The module's scheduled jobs, for the composition root to register.
    """
    return (
        core_scheduler.ScheduledJob(
            delete_revoked_data,
            REVOKED_DATA_DELETE_MINUTES,
            "delete Strava data after Strava access was revoked",
            lock_name=REVOKED_DATA_DELETE_LOCK,
        ),
    )
