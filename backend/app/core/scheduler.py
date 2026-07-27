"""Background scheduler setup for recurring maintenance jobs."""

from collections.abc import Callable, Sequence

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import core.logger as core_logger
import core.network as core_network
import infra.retention as platform_retention
import modules.activities.activity_geocoding.subscribers as activity_geocoding_subscribers
import modules.activities.activity_streams.subscribers as activity_streams_subscribers
import modules.activities.activity_thumbnail.service as activity_thumbnail_service
import modules.auth.maintenance as auth_maintenance
import modules.garmin.activity_utils as garmin_activity_utils
import modules.garmin.health_utils as garmin_health_utils
import modules.strava.activity_utils as strava_activity_utils
import modules.strava.utils as strava_utils

logger = core_logger.get_logger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    """
    Start the scheduler and register recurring jobs.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    if not scheduler.running:
        scheduler.start()

    add_scheduler_job(
        strava_utils.refresh_strava_tokens,
        "interval",
        60,
        [True],
        "refresh Strava user tokens every 60 minutes",
    )

    add_scheduler_job(
        strava_activity_utils.retrieve_strava_users_activities_for_days,
        "interval",
        60,
        [1, True],
        "retrieve last day Strava users activities",
    )

    add_scheduler_job(
        garmin_activity_utils.retrieve_garminconnect_users_activities_for_days,
        "interval",
        60,
        [1],
        "retrieve last day Garmin Connect users activities",
    )

    add_scheduler_job(
        garmin_health_utils.retrieve_garminconnect_users_health_for_days,
        "interval",
        240,
        [1],
        "retrieve last day Garmin Connect users health data",
    )

    add_scheduler_job(
        auth_maintenance.delete_invalid_password_reset_tokens_from_db,
        "interval",
        60,
        [],
        "delete invalid password reset tokens from the database",
    )

    add_scheduler_job(
        auth_maintenance.delete_invalid_sign_up_tokens_from_db,
        "interval",
        60,
        [],
        "delete invalid sign-up tokens from the database",
    )

    add_scheduler_job(
        auth_maintenance.delete_expired_oauth_states_from_db,
        "interval",
        5,
        [],
        "delete expired OAuth states from the database",
    )

    add_scheduler_job(
        auth_maintenance.delete_idp_link_expired_tokens_from_db,
        "interval",
        5,
        [],
        "delete expired IdP link tokens from the database",
    )

    add_scheduler_job(
        auth_maintenance.cleanup_idle_sessions,
        "interval",
        15,
        [],
        "delete expired sessions from the database",
    )

    add_scheduler_job(
        auth_maintenance.cleanup_expired_rotated_tokens,
        "interval",
        1,
        [],
        "delete expired rotated tokens from the database",
    )

    add_scheduler_job(
        auth_maintenance.cleanup_expired_pending_mfa_logins,
        "interval",
        5,
        [],
        "evict expired pending MFA login entries",
    )

    add_scheduler_job(
        activity_thumbnail_service.generate_missing_activity_thumbnails,
        "interval",
        60,
        [],
        "generate thumbnails for activities missing one",
    )

    add_scheduler_job(
        activity_streams_subscribers.run_missing_hr_zone_backfill,
        "interval",
        60,
        [],
        "backfill missing HR zone percentages",
    )

    add_scheduler_job(
        activity_geocoding_subscribers.run_missing_location_backfill,
        "interval",
        60,
        [],
        "backfill missing activity locations (reverse-geocoding)",
    )

    add_scheduler_job(
        core_network.refresh_trusted_proxy_hostnames,
        "interval",
        1,
        [],
        "refresh trusted proxy hostname resolutions",
    )

    # Prune the substrate's append-only bookkeeping tables (event_log, relayed
    # outbox rows, completed jobs) so they don't grow without bound. Self-gated by
    # EVENT_LOG_RETENTION_DAYS / JOBS_RETENTION_DAYS and single-runner via the
    # platform lock. The daily interval keeps them trimmed; the one-shot below
    # clears any backlog promptly and keeps frequently-restarted deployments from
    # starving the daily run.
    add_scheduler_job(
        platform_retention.prune_expired_records,
        "interval",
        1440,
        [],
        "prune expired platform bookkeeping records",
    )
    try:
        scheduler.add_job(
            platform_retention.prune_expired_records,
            "date",
            id="endurain_prune_expired_records_oneshot",
            replace_existing=True,
            misfire_grace_time=None,
        )
        logger.info("Scheduled one-shot retention prune")
    except Exception as err:
        logger.error(f"Failed to schedule one-shot retention prune: {type(err).__name__}", exc_info=err)


def schedule_thumbnail_regeneration() -> None:
    """
    Queue a one-shot full thumbnail regeneration job.

    Runs the heavy delete-and-regenerate pass on the scheduler's
    own executor instead of the request threadpool. Repeated calls
    coalesce into a single pending run via a fixed job id.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    try:
        scheduler.add_job(
            activity_thumbnail_service.delete_and_regenerate_all_activity_thumbnails,
            "date",
            id="endurain_regenerate_all_thumbnails",
            replace_existing=True,
            misfire_grace_time=None,
        )
        logger.info("Scheduled one-shot thumbnail regeneration job")
    except Exception as err:
        logger.error(f"Failed to schedule thumbnail regeneration job: {type(err).__name__}", exc_info=err)


def schedule_missing_thumbnail_generation() -> None:
    """
    Queue a one-shot missing-thumbnail generation job.

    Used at startup so the potentially heavy generation pass runs
    on the scheduler's own executor after the app is ready, instead
    of blocking the lifespan startup (which would delay uvicorn from
    accepting connections). Repeated calls coalesce into a single
    pending run via a fixed job id.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    try:
        scheduler.add_job(
            activity_thumbnail_service.generate_missing_activity_thumbnails,
            "date",
            id="endurain_generate_missing_thumbnails_oneshot",
            replace_existing=True,
            misfire_grace_time=None,
        )
        logger.info("Scheduled one-shot missing thumbnail generation job")
    except Exception as err:
        logger.error(f"Failed to schedule missing thumbnail generation job: {type(err).__name__}", exc_info=err)


def schedule_missing_hr_zone_backfill() -> None:
    """
    Queue a one-shot missing HR-zone backfill job.

    Used at startup so the potentially heavy backfill runs on the
    scheduler's own executor after the app is ready, instead of
    blocking the lifespan startup. Repeated calls coalesce into a
    single pending run via a fixed job id.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    try:
        scheduler.add_job(
            activity_streams_subscribers.run_missing_hr_zone_backfill,
            "date",
            id="endurain_backfill_missing_hr_zones_oneshot",
            replace_existing=True,
            misfire_grace_time=None,
        )
        logger.info("Scheduled one-shot HR-zone backfill job")
    except Exception as err:
        logger.error(f"Failed to schedule HR-zone backfill job: {type(err).__name__}", exc_info=err)


def schedule_missing_location_backfill() -> None:
    """
    Queue a one-shot missing activity-location backfill job.

    Used at startup so the potentially heavy, network-bound reverse-geocoding
    backfill runs on the scheduler's own executor after the app is ready, instead
    of blocking the lifespan startup. Repeated calls coalesce into a single
    pending run via a fixed job id.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    try:
        scheduler.add_job(
            activity_geocoding_subscribers.run_missing_location_backfill,
            "date",
            id="endurain_backfill_missing_locations_oneshot",
            replace_existing=True,
            misfire_grace_time=None,
        )
        logger.info("Scheduled one-shot activity-location backfill job")
    except Exception as err:
        logger.error(f"Failed to schedule activity-location backfill job: {type(err).__name__}", exc_info=err)


def _scheduler_job_id(description: str) -> str:
    """
    Build a stable scheduler job ID from its description.

    Args:
        description: Human-readable job description.

    Returns:
        Stable APScheduler job identifier.

    Raises:
        None.
    """
    return "endurain_" + "_".join(description.lower().split())


def add_scheduler_job(
    func: Callable[..., object],
    interval: str,
    minutes: int,
    args: Sequence[object],
    description: str,
) -> None:
    """
    Register or replace a recurring scheduler job.

    Args:
        func: Callable to execute.
        interval: APScheduler trigger name.
        minutes: Interval length in minutes.
        args: Positional arguments passed to func.
        description: Human-readable job description.

    Returns:
        None.

    Raises:
        None.
    """
    try:
        logger.info(f"Added scheduler job to {description} every {minutes} minutes")
        scheduler.add_job(
            func,
            interval,
            minutes=minutes,
            args=list(args),
            id=_scheduler_job_id(description),
            replace_existing=True,
        )
    except Exception as err:
        logger.error(f"Failed to add scheduler job to {description}: {type(err).__name__}", exc_info=err)


def stop_scheduler() -> None:
    """
    Stop the scheduler if it is running.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    if scheduler.running:
        scheduler.shutdown(wait=False)
