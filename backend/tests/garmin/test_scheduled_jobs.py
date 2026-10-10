"""Tests for Garmin Connect recurring job declarations."""

import modules.garmin.scheduled_jobs as garmin_scheduled_jobs


def test_every_garmin_job_has_a_distinct_coordination_lock():
    """Keep each recurring Garmin operation single-runner across replicas."""
    jobs = garmin_scheduled_jobs.recurring_jobs()

    assert all(job.lock_name for job in jobs)
    assert len({job.lock_name for job in jobs}) == len(jobs)
