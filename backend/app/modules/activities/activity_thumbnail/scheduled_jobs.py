"""Scheduled work owned by the activity-thumbnail package."""

import core.scheduler as core_scheduler
import modules.activities.activity_thumbnail.integration_service as thumbnail_integration


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return thumbnail reconciliation jobs."""
    return (
        core_scheduler.ScheduledJob(
            thumbnail_integration.generate_missing_thumbnails,
            60,
            "generate thumbnails for activities missing one",
        ),
    )


def schedule_missing_thumbnail_generation() -> None:
    """Queue one thumbnail reconciliation pass."""
    core_scheduler.run_once(
        thumbnail_integration.generate_missing_thumbnails,
        job_id="endurain_generate_missing_thumbnails_oneshot",
        description="missing thumbnail generation",
    )


def schedule_thumbnail_regeneration() -> None:
    """Queue a delete-and-regenerate pass over every thumbnail."""
    core_scheduler.run_once(
        thumbnail_integration.regenerate_all_thumbnails,
        job_id="endurain_regenerate_all_thumbnails",
        description="thumbnail regeneration",
    )
