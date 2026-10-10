"""Tests for Strava recurring job declarations."""

import modules.strava.scheduled_jobs as strava_scheduled_jobs


def test_every_strava_job_has_a_distinct_coordination_lock():
    """Keep each recurring Strava operation single-runner across replicas."""
    jobs = strava_scheduled_jobs.recurring_jobs()

    assert all(job.lock_name for job in jobs)
    assert len({job.lock_name for job in jobs}) == len(jobs)
