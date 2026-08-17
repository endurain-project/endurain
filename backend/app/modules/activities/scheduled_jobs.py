"""The activities module's scheduled work, declared by the module that owns it.

The counterpart of :mod:`~modules.activities.subscriber_registry` for time-driven
work rather than event-driven: the composition root collects
:func:`recurring_jobs` and hands it to the scheduler, so ``core.scheduler`` never
learns that activities exist.

Three of the four recurring jobs are the **reconciliation nets** declared in
``subscriber_registry.ACTIVITY_DURABLE_SUBSCRIBER_NETS`` — the scheduled backfills
that re-derive anything a durable subscriber missed. The one-shot variants below
run the same passes once at startup, on the scheduler's executor rather than
inline, so a heavy backfill cannot delay the app from accepting connections.
"""

import core.scheduler as core_scheduler
import modules.activities.activity_geocoding.subscribers as activity_geocoding_subscribers
import modules.activities.activity_ingestion.ingestion_jobs as activity_ingestion_jobs
import modules.activities.activity_streams.subscribers as activity_streams_subscribers
import modules.activities.activity_thumbnail.service as activity_thumbnail_service


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """
    Return the activities module's recurring scheduled jobs.

    Args:
        None.

    Returns:
        The module's scheduled jobs, for the composition root to register.

    Raises:
        None.
    """
    return (
        core_scheduler.ScheduledJob(
            activity_thumbnail_service.generate_missing_activity_thumbnails,
            60,
            "generate thumbnails for activities missing one",
        ),
        core_scheduler.ScheduledJob(
            activity_streams_subscribers.run_missing_hr_zone_backfill,
            60,
            "backfill missing HR zone percentages",
        ),
        core_scheduler.ScheduledJob(
            activity_geocoding_subscribers.run_missing_location_backfill,
            60,
            "backfill missing activity locations (reverse-geocoding)",
        ),
        # Same window and cadence as the substrate's own prune, but declared here
        # because activity_upload_jobs is a domain table: infra.retention must
        # not import a domain module.
        core_scheduler.ScheduledJob(
            activity_ingestion_jobs.prune_expired_ingestion_jobs,
            1440,
            "prune expired activity ingestion jobs",
        ),
    )


def schedule_missing_thumbnail_generation() -> None:
    """
    Queue a one-shot generation pass for activities missing a thumbnail.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    core_scheduler.run_once(
        activity_thumbnail_service.generate_missing_activity_thumbnails,
        job_id="endurain_generate_missing_thumbnails_oneshot",
        description="missing thumbnail generation",
    )


def schedule_missing_hr_zone_backfill() -> None:
    """
    Queue a one-shot backfill for streams missing HR-zone percentages.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    core_scheduler.run_once(
        activity_streams_subscribers.run_missing_hr_zone_backfill,
        job_id="endurain_backfill_missing_hr_zones_oneshot",
        description="HR-zone backfill",
    )


def schedule_missing_location_backfill() -> None:
    """
    Queue a one-shot reverse-geocoding backfill for activities missing a location.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    core_scheduler.run_once(
        activity_geocoding_subscribers.run_missing_location_backfill,
        job_id="endurain_backfill_missing_locations_oneshot",
        description="activity-location backfill",
    )


def schedule_thumbnail_regeneration() -> None:
    """
    Queue a one-shot delete-and-regenerate pass over every thumbnail.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    core_scheduler.run_once(
        activity_thumbnail_service.delete_and_regenerate_all_activity_thumbnails,
        job_id="endurain_regenerate_all_thumbnails",
        description="thumbnail regeneration",
    )
