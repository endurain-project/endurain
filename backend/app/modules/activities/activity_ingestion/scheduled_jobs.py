"""Scheduled work owned by activity ingestion."""

import core.scheduler as core_scheduler
import modules.activities.activity_ingestion.integration_service as activity_ingestion


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return ingestion retention jobs."""
    return (
        core_scheduler.ScheduledJob(
            activity_ingestion.prune_expired_ingestion_jobs,
            1440,
            "prune expired activity ingestion jobs",
        ),
    )
