"""Tests for Garmin Connect recurring job declarations."""

from unittest.mock import patch

import modules.garmin.scheduled_jobs as garmin_scheduled_jobs


def test_every_garmin_job_has_a_distinct_coordination_lock():
    """Keep each recurring Garmin operation single-runner across replicas."""
    jobs = garmin_scheduled_jobs.recurring_jobs()

    assert all(job.lock_name for job in jobs)
    assert len({job.lock_name for job in jobs}) == len(jobs)


def test_the_activity_pull_is_not_a_garmin_job_any_more():
    """It is one refresh job per linked user, queued by activity ingestion."""
    assert "garmin_activity_sync" not in {job.lock_name for job in garmin_scheduled_jobs.recurring_jobs()}


def test_the_startup_health_pull_is_queued_under_the_recurring_jobs_lock():
    """Startup neither waits on the pull nor lets every replica run it."""
    (recurring,) = garmin_scheduled_jobs.recurring_jobs()

    with patch.object(garmin_scheduled_jobs.core_scheduler, "run_once") as run_once:
        garmin_scheduled_jobs.schedule_recent_health()

    run_once.assert_called_once()
    assert run_once.call_args.args == (garmin_scheduled_jobs.sync_recent_health,)
    assert run_once.call_args.kwargs["lock_name"] == recurring.lock_name
    assert recurring.func is garmin_scheduled_jobs.sync_recent_health
