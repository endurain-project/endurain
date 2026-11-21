"""The Garmin Connect module's scheduled work: its recurring job and the startup pull, on the real scheduler."""

import jasil.runtime as jasil_runtime
import pytest
from jasil.events import Event

import core.config as core_config
import core.scheduler as core_scheduler
import modules.garmin.events as garmin_events
import modules.garmin.scheduled_jobs as garmin_scheduled_jobs

_ONE_SHOT_ID = "endurain_garmin_recent_health_oneshot"


def test_every_garmin_job_has_a_distinct_coordination_lock():
    """Keep each recurring Garmin operation single-runner across replicas."""
    jobs = garmin_scheduled_jobs.recurring_jobs()

    assert all(job.lock_name for job in jobs)
    assert len({job.lock_name for job in jobs}) == len(jobs)


def test_the_activity_pull_is_not_a_garmin_job_any_more():
    """It is one refresh job per linked user, queued by activity ingestion."""
    assert "garmin_activity_sync" not in {job.lock_name for job in garmin_scheduled_jobs.recurring_jobs()}


@pytest.fixture
def one_shot_job():
    """Return a function that reads the pending one-shot health pull off the scheduler, which the test removes."""
    yield lambda: core_scheduler.scheduler.get_job(_ONE_SHOT_ID)
    if core_scheduler.scheduler.get_job(_ONE_SHOT_ID) is not None:
        core_scheduler.scheduler.remove_job(_ONE_SHOT_ID)


def test_the_startup_health_pull_is_queued_under_the_recurring_jobs_lock_and_queues_every_linked_user(
    linked, one_shot_job, monkeypatch
):
    """Startup neither waits on the pull nor lets every replica run it."""
    monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
    events: list[Event] = []
    jasil_runtime.get_active_platform().events.subscribe(garmin_events.GARMIN_SYNC_REQUESTED, events.append)
    (recurring,) = garmin_scheduled_jobs.recurring_jobs()

    garmin_scheduled_jobs.schedule_recent_health()

    job = one_shot_job()
    assert job is not None
    assert job.args == (recurring.lock_name, garmin_scheduled_jobs.sync_recent_health)
    assert events == []
    job.func(*job.args)
    assert [event.payload["user_id"] for event in events] == [str(linked.id)]
    assert recurring.func is garmin_scheduled_jobs.sync_recent_health
