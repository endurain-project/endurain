"""Scheduled passes run under the scheduler's distributed lock, one replica at a time."""

import modules.activities.activity_file_storage.scheduled_jobs as file_jobs
import modules.activities.activity_ingestion.scheduled_jobs as ingestion_jobs
import modules.activities.activity_media.scheduled_jobs as media_jobs
import modules.activities.activity_thumbnail.scheduled_jobs as thumbnail_jobs


def test_each_sweep_declares_its_lock():
    assert [job.lock_name for job in media_jobs.recurring_jobs()] == [media_jobs.SWEEP_LOCK_NAME]
    assert [job.lock_name for job in file_jobs.recurring_jobs()] == [file_jobs.SWEEP_LOCK_NAME]
    sweep = next(job for job in thumbnail_jobs.recurring_jobs() if job.func is thumbnail_jobs.sweep_orphaned_thumbnails)
    assert sweep.lock_name == thumbnail_jobs.SWEEP_LOCK_NAME


def test_each_ingestion_pass_declares_its_lock():
    locks = {job.func.__name__: job.lock_name for job in ingestion_jobs.recurring_jobs()}

    assert locks == {
        "prune_expired_ingestion_jobs": ingestion_jobs.PRUNE_LOCK_NAME,
        "enqueue_provider_refreshes": ingestion_jobs.REFRESH_FANOUT_LOCK_NAME,
        "redispatch_deferred_refreshes": ingestion_jobs.DEFERRED_REDISPATCH_LOCK_NAME,
        "fail_stale_ingestion_jobs": ingestion_jobs.STALE_JOBS_LOCK_NAME,
        "sweep_stale_staged_blobs": ingestion_jobs.STAGED_SWEEP_LOCK_NAME,
    }
    assert len(set(locks.values())) == len(locks), "two passes share a lock, so one would starve the other"


def test_the_startup_catch_up_passes_hold_the_same_lock_as_the_scheduled_ones():
    """A restart's one-shot pass must not run beside the scheduled one on another replica."""
    from unittest.mock import patch

    for name, one_shot, lock in (
        (
            "schedule_provider_refresh",
            ingestion_jobs.schedule_provider_refresh,
            ingestion_jobs.REFRESH_FANOUT_LOCK_NAME,
        ),
        (
            "schedule_missing_thumbnail_generation",
            thumbnail_jobs.schedule_missing_thumbnail_generation,
            thumbnail_jobs.BACKFILL_LOCK_NAME,
        ),
    ):
        with patch("core.scheduler.run_once") as run_once:
            one_shot()
        assert run_once.call_args.kwargs["lock_name"] == lock, name


def test_the_thumbnail_backfill_and_regeneration_share_one_lock():
    """They touch the same thumbnails, so they exclude each other; only the backfill is skipped when it is held."""
    import modules.activities.activity_thumbnail.service as thumbnail_service

    backfill = next(
        job for job in thumbnail_jobs.recurring_jobs() if job.func is thumbnail_jobs.generate_missing_thumbnails
    )

    assert backfill.lock_name == thumbnail_service.BACKFILL_LOCK_NAME
